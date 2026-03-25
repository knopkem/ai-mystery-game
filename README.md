# AI Murder Mystery

A **turn-based 2D murder mystery** game where NPCs are controlled by a locally-running fine-tuned LLM. Each playthrough is unique — the killer, motive, evidence placement, and NPC behaviours are all dynamically generated and driven by the model. Fully playable offline with rich rule-based fallbacks when no LLM server is running.

## Concept

The player is a detective investigating a murder in a Victorian mansion. 5 suspects roam 5 rooms. Each game turn, NPCs autonomously decide to move, hide/destroy evidence, coordinate alibis, or plant false clues — driven by a local fine-tuned language model. The player must interrogate suspects (whose responses are also LLM-generated) and accuse the correct killer before 15 turns pass.

## Stack

| Component | Technology |
|-----------|-----------|
| Game Engine | **Pygame-CE** (Python, programmatic UI — no assets needed) |
| LLM Server | Python + FastAPI |
| Base Model | **Llama 3.1 8B** (mlx-community 4-bit, ~4 GB) |
| Fine-tuning | **mlx-tune** (Unsloth-compatible, Apple Silicon native) |
| Inference | **mlx-lm** (MLX native) / llama-cpp-python (GGUF fallback) |
| Training data | ~2700 synthetic examples generated via Anthropic Claude |
| Communication | HTTP REST (localhost:8000) |

**Target hardware**: MacBook M4, 16 GB RAM (~4 GB model, ~200 MB game)

## Project Structure

```
ai-game/
├── pygame-game/         # Pygame game (fully self-contained, runs offline)
│   ├── main.py          # Entry point
│   ├── controller.py    # Game loop, event handling (Screen/Overlay enums)
│   ├── game/
│   │   ├── constants.py # Rooms, evidence items, suspect blueprints
│   │   ├── state.py     # GameState, Phase enum
│   │   ├── client.py    # Async LLM HTTP client
│   │   └── fallbacks.py # Offline fallbacks (rule-based + training-data sampler)
│   ├── ui/
│   │   ├── theme.py     # HiDPI/Retina support, colours, fonts, layout
│   │   ├── widgets.py   # Button, TextInput, draw_text()
│   │   ├── map_view.py  # Room map drawing
│   │   ├── hud.py       # HUD, side panel, game log
│   │   ├── overlays.py  # Interrogate / Accuse / Notes overlays
│   │   └── screens.py   # Title, tutorial, loading, game-over screens
│   └── requirements.txt # pygame-ce, requests
├── llm-server/          # FastAPI inference server
│   ├── server.py        # API endpoints (/setup-mystery, /npc-actions, /interrogate)
│   ├── prompts.py       # Prompt templates for each endpoint
│   ├── schemas.py       # Pydantic request/response models
│   ├── fallback.py      # Server-side rule-based fallbacks
│   ├── .env.example     # Config template (BACKEND, MLX_MODEL_PATH)
│   └── model/           # Model files go here (gitignored)
├── training/            # Fine-tuning pipeline (Apple Silicon)
│   ├── generate_data.py # ~2700 synthetic examples via Anthropic Claude
│   ├── train.py         # mlx-tune LoRA fine-tuning (Air-optimised)
│   ├── export_gguf.py   # Optional GGUF export for cross-platform deploy
│   ├── evaluate.py      # Quality evaluation script
│   └── data/            # Generated JSONL training data (gitignored)
└── docs/
    └── game-design.md   # Full game design document
```

## Getting Started

### Option A — Play immediately (no LLM, offline fallbacks)

```bash
cd pygame-game
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The game runs fully offline using rule-based interrogation fallbacks and training-data-sampled NPC actions. All core gameplay works — it just won't have dynamic LLM-generated dialogue.

---

### Option B — Play with the base Llama 3.1 8B (no fine-tuning required)

#### 1. Set up and start the LLM server

```bash
cd llm-server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install huggingface_hub

# Download Llama 3.1 8B 4-bit (~4 GB, one-time)
# The HF_TOKEN is optional (but it might be very slow to download then -> better create a free account and generate a token)
HF_TOKEN=hf_your_token python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Meta-Llama-3.1-8B-Instruct-4bit', local_dir='model/mlx-model')
"

cp .env.example .env    # default settings are correct for Llama 3.1 8B
uvicorn server:app --host 127.0.0.1 --port 8000
```

#### 2. Run the game

```bash
cd ../pygame-game
source .venv/bin/activate
python main.py
```

The title screen shows **✓ LLM server online**. NPC behaviour and interrogation responses are now fully LLM-driven.

---

### Option C — Fine-tune on your game data (best results)

#### 1. Generate training data (~2700 examples via Claude) - can be skipped (already included)

```bash
cd training
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-train.txt

ANTHROPIC_API_KEY=sk-ant-... python generate_data.py
# Saves to data/npc_actions.jsonl, data/interrogations.jsonl, data/mystery_setups.jsonl
# Resumes automatically if interrupted
```

#### 2. Fine-tune (Apple Silicon, MacBook Air safe)

```bash
python train.py
# Default: Llama 3.1 8B, batch=1, 5-min cooldown between epochs
# Checkpoint saved every 50 steps — crash-safe
# Takes ~2.5 hours on M4 Air (lid open, hard surface recommended)

# Other model options:
python train.py --model mlx-community/Phi-3.5-mini-instruct-4bit   # faster
python train.py --model mlx-community/Mistral-7B-Instruct-v0.3-4bit
python train.py --cooldown 0   # disable cooldown (MacBook Pro / Mac Studio)
```

#### 3. Deploy and run

```bash
cp -r checkpoints/mlx-model ../llm-server/model/mlx-model
cd ../llm-server && uvicorn server:app --host 127.0.0.1 --port 8000
```

---

## Gameplay

- **Objective**: Identify the killer and motive before 15 turns expire
- **2 action points per turn**: Move, Examine evidence, Interrogate suspect, Accuse, Review notes
- **NPC phase**: Each suspect autonomously acts (LLM-driven or offline fallback)
- **Pressure system**: Each interrogation raises an NPC's pressure (0–10); killers crack under high pressure
- **Win**: Correct suspect + correct motive
- **Lose**: Wrong accusation, all critical evidence destroyed, or 15 turns pass

## Offline Fallback Architecture

When the LLM server is unavailable:

| Feature | Offline behaviour |
|---------|------------------|
| Mystery setup | Rule-based random assignment (killer, motive, evidence, alibis) |
| NPC actions | Sampled from training data (1485 examples), matched by killer-status + personality + pressure |
| Interrogation | Keyword-matched rule engine — alibi, motive, secrets, evidence, accusation branches |

The game is fully playable offline — the fallback is noticeably simpler than the LLM but still provides a solvable mystery.

## NPC Action Schema

```json
{
  "action": "hide_evidence",
  "target": "kitchen_knife",
  "secondary_target": null,
  "internal_thought": "The detective is getting too close. I need to move the knife."
}
```

Interrogation response:
```json
{
  "dialogue": "I was in the library all evening, I tell you.",
  "lie": true,
  "emotion": "defensive",
  "internal_thought": "I can't let them know I was in the kitchen."
}
```

## Why mlx-tune instead of Unsloth?

Unsloth requires Triton which is CUDA-only and unavailable on macOS.
[`mlx-tune`](https://github.com/ARahim3/mlx-tune) is a community-built drop-in replacement
with an identical API (`FastLanguageModel`, `SFTTrainer`) that runs natively on Apple Silicon.
Inference uses [`mlx-lm`](https://github.com/ml-explore/mlx-lm) — also native MLX.
GGUF export via `export_gguf.py` is available for cross-platform deployment.

