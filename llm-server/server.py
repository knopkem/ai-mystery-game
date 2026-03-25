"""
FastAPI server exposing LLM-driven NPC endpoints for the murder mystery game.

Endpoints
---------
POST /setup-mystery    — Generate a new mystery (killer, evidence, alibis)
POST /npc-actions      — Batch NPC decisions for a game turn
POST /interrogate      — Single NPC interrogation response
GET  /health           — Liveness check (reports model load status)
"""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from fallback import fallback_all_npc_actions, fallback_npc_action
from prompts import (
    build_batch_npc_action_prompt,
    build_interrogate_prompt,
    build_setup_mystery_prompt,
)
from schemas import (
    InterrogateRequest,
    InterrogateResponse,
    MysterySetup,
    NpcActionResult,
    NpcActionsRequest,
    NpcActionsResponse,
    SetupMysteryRequest,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("murder-mystery")

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

MODEL_PATH = Path(os.getenv("MODEL_PATH", "model/murder-mystery.gguf"))
N_CTX = int(os.getenv("N_CTX", "4096"))
N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", "-1"))  # -1 = all layers on Metal
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
MAX_RETRIES = 3

_llm = None  # llama_cpp.Llama instance, loaded on startup


def _load_model() -> object | None:
    try:
        from llama_cpp import Llama  # type: ignore
        if not MODEL_PATH.exists():
            log.warning(
                "Model file not found at %s. Server will use fallback logic only.", MODEL_PATH
            )
            return None
        log.info("Loading model from %s ...", MODEL_PATH)
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=N_CTX,
            n_gpu_layers=N_GPU_LAYERS,
            verbose=False,
        )
        log.info("Model loaded successfully.")
        return llm
    except Exception as exc:
        log.error("Failed to load model: %s", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm
    _llm = _load_model()
    yield
    _llm = None


app = FastAPI(
    title="Murder Mystery LLM Server",
    description="Local LLM inference server for AI-driven NPC behavior.",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# LLM call helper
# ---------------------------------------------------------------------------

def _call_llm(system: str, user: str) -> str | None:
    """Call the model; return raw text or None on failure."""
    if _llm is None:
        return None
    try:
        response = _llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.7,
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.error("LLM inference error: %s", exc)
        return None


def _extract_json(text: str) -> str:
    """Strip markdown fences and extract the first JSON object or array."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find outermost { } or [ ]
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start=start):
                if ch == start_char:
                    depth += 1
                elif ch == end_char:
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
    return text


def _parse_with_retry(system: str, user: str, schema_cls: type, retries: int = MAX_RETRIES):
    """Call LLM up to `retries` times; parse into schema_cls or return None."""
    for attempt in range(retries):
        raw = _call_llm(system, user)
        if raw is None:
            return None
        try:
            return schema_cls.model_validate(json.loads(_extract_json(raw)))
        except Exception as exc:
            log.warning("Parse attempt %d/%d failed: %s", attempt + 1, retries, exc)
    return None


def _parse_list_with_retry(system: str, user: str, item_cls: type, retries: int = MAX_RETRIES):
    """Call LLM up to `retries` times; parse into list[item_cls] or return None."""
    for attempt in range(retries):
        raw = _call_llm(system, user)
        if raw is None:
            return None
        try:
            parsed = json.loads(_extract_json(raw))
            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array")
            return [item_cls.model_validate(item) for item in parsed]
        except Exception as exc:
            log.warning("Parse attempt %d/%d failed: %s", attempt + 1, retries, exc)
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _llm is not None}


@app.post("/setup-mystery", response_model=MysterySetup)
def setup_mystery(req: SetupMysteryRequest):
    """Generate a new mystery scenario at the start of a game."""
    from prompts import build_setup_mystery_prompt
    system, user = build_setup_mystery_prompt(req.suspects, req.rooms, req.evidence_items)

    result = _parse_with_retry(system, user, MysterySetup)
    if result is None:
        log.error("/setup-mystery: LLM failed or unavailable, returning 503")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model unavailable. Ensure the GGUF model is loaded.",
        )
    log.info("/setup-mystery: killer=%s, motive=%s", result.killer_name, result.motive)
    return result


@app.post("/npc-actions", response_model=NpcActionsResponse)
def npc_actions(req: NpcActionsRequest):
    """Return a batch of NPC actions for the current game turn."""
    system, user = build_batch_npc_action_prompt(req.game_state.npcs, req.game_state)

    results: list[NpcActionResult] | None = _parse_list_with_retry(
        system, user, NpcActionResult
    )

    if results is None:
        log.warning("/npc-actions: using fallback logic")
        results = fallback_all_npc_actions(req.game_state.npcs, req.game_state)

    log.info(
        "/npc-actions: turn=%d, actions=%s",
        req.game_state.turn_number,
        [(r.npc_name, r.action) for r in results],
    )
    return NpcActionsResponse(actions=results)


@app.post("/interrogate", response_model=InterrogateResponse)
def interrogate(req: InterrogateRequest):
    """Return an NPC's response to a player interrogation."""
    system, user = build_interrogate_prompt(
        req.npc_state,
        req.player_question,
        req.evidence_shown,
        req.game_state,
    )

    result = _parse_with_retry(system, user, InterrogateResponse)

    if result is None:
        log.warning("/interrogate: using fallback response for %s", req.npc_state.identity.name)
        result = InterrogateResponse(
            dialogue="I... I don't know what you want from me.",
            lie=False,
            emotion="nervous",
            internal_thought="(fallback) LLM unavailable.",
        )

    log.info(
        "/interrogate: npc=%s, emotion=%s, lie=%s",
        req.npc_state.identity.name,
        result.emotion,
        result.lie,
    )
    return result
