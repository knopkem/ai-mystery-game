"""
FastAPI server exposing LLM-driven NPC endpoints for the murder mystery game.

Endpoints
---------
POST /setup-mystery    — Generate a new mystery (killer, evidence, alibis)
POST /npc-actions      — Batch NPC decisions for a game turn
POST /interrogate      — Single NPC interrogation response
GET  /health           — Liveness check (reports model load status)

Inference backends (set via .env or environment variable BACKEND):
  mlx       (default) — Apple Silicon native via mlx-lm; uses MLX-format model at MLX_MODEL_PATH
  llamacpp             — Cross-platform via llama-cpp-python; uses GGUF at MODEL_PATH
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
# Config
# ---------------------------------------------------------------------------

BACKEND = os.getenv("BACKEND", "mlx").lower()  # "mlx" (default) or "llamacpp"

# MLX backend (Apple Silicon — recommended)
MLX_MODEL_PATH = os.getenv("MLX_MODEL_PATH", "model/mlx-model")

# llama-cpp backend (cross-platform GGUF fallback)
MODEL_PATH = Path(os.getenv("MODEL_PATH", "model/murder-mystery.gguf"))
N_CTX = int(os.getenv("N_CTX", "4096"))
N_GPU_LAYERS = int(os.getenv("N_GPU_LAYERS", "-1"))  # -1 = all layers on Metal

MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
MAX_RETRIES = 3

_llm = None          # llama_cpp.Llama instance (llamacpp backend)
_mlx_model = None    # mlx-lm model (mlx backend)
_mlx_tokenizer = None


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_model_mlx() -> tuple[object, object] | tuple[None, None]:
    """Load MLX-format model via mlx-lm (Apple Silicon native)."""
    try:
        import mlx_lm  # type: ignore
        from pathlib import Path as _Path
        if not _Path(MLX_MODEL_PATH).exists():
            log.warning(
                "MLX model not found at %s. Server will use fallback logic only.", MLX_MODEL_PATH
            )
            return None, None
        log.info("Loading MLX model from %s ...", MLX_MODEL_PATH)
        model, tokenizer = mlx_lm.load(MLX_MODEL_PATH)
        log.info("MLX model loaded successfully.")
        return model, tokenizer
    except Exception as exc:
        log.error("Failed to load MLX model: %s", exc)
        return None, None


def _load_model_llamacpp() -> object | None:
    """Load GGUF model via llama-cpp-python (cross-platform fallback)."""
    try:
        from llama_cpp import Llama  # type: ignore
        if not MODEL_PATH.exists():
            log.warning(
                "GGUF model not found at %s. Server will use fallback logic only.", MODEL_PATH
            )
            return None
        log.info("Loading GGUF model from %s ...", MODEL_PATH)
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=N_CTX,
            n_gpu_layers=N_GPU_LAYERS,
            verbose=False,
        )
        log.info("GGUF model loaded successfully.")
        return llm
    except Exception as exc:
        log.error("Failed to load GGUF model: %s", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _llm, _mlx_model, _mlx_tokenizer
    if BACKEND == "mlx":
        log.info("Backend: mlx-lm (Apple Silicon MLX)")
        _mlx_model, _mlx_tokenizer = _load_model_mlx()
    else:
        log.info("Backend: llama-cpp-python (GGUF)")
        _llm = _load_model_llamacpp()
    yield
    _llm = None
    _mlx_model = None
    _mlx_tokenizer = None


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
    """Call the active backend; return raw text or None on failure."""
    if BACKEND == "mlx":
        return _call_mlx(system, user)
    return _call_llamacpp(system, user)


def _call_mlx(system: str, user: str) -> str | None:
    """Inference via mlx-lm (Apple Silicon native)."""
    if _mlx_model is None or _mlx_tokenizer is None:
        return None
    try:
        import mlx_lm  # type: ignore
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = _mlx_tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        return mlx_lm.generate(
            _mlx_model, _mlx_tokenizer,
            prompt=prompt,
            max_tokens=MAX_TOKENS,
            verbose=False,
        ).strip()
    except Exception as exc:
        log.error("MLX inference error: %s", exc)
        return None


def _call_llamacpp(system: str, user: str) -> str | None:
    """Inference via llama-cpp-python (GGUF, cross-platform fallback)."""
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
        log.error("llama-cpp inference error: %s", exc)
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
    if BACKEND == "mlx":
        loaded = _mlx_model is not None
    else:
        loaded = _llm is not None
    return {"status": "ok", "backend": BACKEND, "model_loaded": loaded}


@app.post("/setup-mystery", response_model=MysterySetup)
def setup_mystery(req: SetupMysteryRequest):
    """Generate a new mystery scenario at the start of a game."""
    from prompts import build_setup_mystery_prompt
    system, user = build_setup_mystery_prompt(
        req.suspects,
        req.rooms,
        req.evidence_items,
        forced_killer=req.forced_killer,
        forced_positions=req.forced_positions,
        forced_evidence_placements=req.forced_evidence_placements,
    )

    result = _parse_with_retry(system, user, MysterySetup)
    if result is None:
        log.error("/setup-mystery: LLM failed or unavailable, returning 503")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model unavailable. Ensure the GGUF model is loaded.",
        )

    # Hard-override structural fields with pre-randomised values from the
    # client.  LLMs often ignore prompt constraints; doing this server-side
    # guarantees variety regardless of what the model actually output.
    if req.forced_killer:
        result.killer_name = req.forced_killer
    if req.forced_positions:
        result.initial_npc_positions = req.forced_positions
    if req.forced_evidence_placements:
        result.evidence_placements = req.forced_evidence_placements

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
