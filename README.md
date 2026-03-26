# AI Murder Mystery

A **turn-based 2D murder mystery** game where NPCs are controlled by a locally-running fine-tuned LLM. Each playthrough is unique — the killer, motive, evidence placement, and NPC behaviours are all dynamically generated and driven by the model. Fully playable offline with rich rule-based fallbacks when no LLM server is running.

## Concept

The player is a detective investigating a murder in a Victorian mansion. 5 suspects roam 5 rooms. Each game turn, NPCs autonomously decide to move, hide/destroy evidence, coordinate alibis, or plant false clues — driven by a local fine-tuned language model. The player must interrogate suspects (whose responses are also LLM-generated) and accuse the correct killer before 15 turns pass.

## Stack

| Component | Technology |
|-----------|-----------|
| Game Engine | **Pygame-CE** (Python, programmatic UI — no assets needed) |
| LLM Server | Python + FastAPI |
| Base Model | **Llama 3.1 8B** (4-bit quantized, ~4–5 GB) |
| Fine-tuning | **mlx-tune** (Apple Silicon) · **Unsloth + TRL** (NVIDIA / AMD GPU) |
| Inference | **mlx-lm** (Apple Silicon) · **llama-cpp-python** (GGUF, all platforms) |
| Training data | ~2700 synthetic examples generated via Anthropic Claude |
| Communication | HTTP REST (localhost:8000) |

**Supported training hardware**

| Platform | Requirements | Notes |
|----------|-------------|-------|
| Apple Silicon | macOS, 16 GB RAM | `mlx-tune` — no CUDA/Triton needed |
| NVIDIA GPU | CUDA 11.8+, 6 GB+ VRAM | `unsloth` + `trl` + `bitsandbytes` |
| AMD GPU | ROCm 7.2+, 6 GB+ VRAM | `unsloth` + `trl` + `bitsandbytes` (ROCm wheels) — **Linux / WSL2 only** |

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
├── training/            # Fine-tuning pipeline (MLX / CUDA / ROCm)
│   ├── generate_data.py      # ~2700 synthetic examples via Anthropic Claude
│   ├── train.py              # LoRA fine-tuning — auto-detects hardware backend
│   ├── export_gguf.py        # GGUF export for cross-platform llama-cpp deploy
│   ├── evaluate.py           # Quality evaluation script
│   ├── requirements-train.txt       # Apple Silicon (mlx-tune)
│   ├── requirements-train-cuda.txt  # NVIDIA CUDA (unsloth + trl)
│   ├── requirements-train-rocm.txt  # AMD ROCm  (unsloth + trl)
│   └── data/                 # Generated JSONL training data (gitignored)
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

### Recommended models

| Model | Tag | Why? |
|---|---|---|
| **Llama 3.1 8B** | Top Choice | Highly optimized for MLX. Fits comfortably in 4-bit with room for a 4k context window. |
| **Mistral 7B v0.3** | Great Alternative | Very stable on Mac; slightly smaller memory footprint than Llama 3.1. |
| **Phi-3.5 Mini (3.8B)** | Speed King | Trains incredibly fast on an M4. Can use a larger context window (8k+). |
| **Gemma 2 9B** | Experimental | Fits on 16 GB but it's a tight squeeze — keep batch sizes at 1. |

All models above are available as MLX 4-bit quantizations on the `mlx-community` HuggingFace namespace. For NVIDIA/AMD, use the corresponding GGUF from `bartowski` or `unsloth`.

---

### Option B — Play with the base Llama 3.1 8B (no fine-tuning required)

#### 1. Set up and start the LLM server

```bash
cd llm-server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install huggingface_hub
```

**Download the model** (choose one, ~4 GB, one-time):

```bash
# Apple Silicon — MLX 4-bit (fastest on macOS)
HF_TOKEN=hf_your_token python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Meta-Llama-3.1-8B-Instruct-4bit', local_dir='model/mlx-model')
"

# NVIDIA / AMD — GGUF 4-bit (for llama-cpp-python)
HF_TOKEN=hf_your_token python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download('bartowski/Meta-Llama-3.1-8B-Instruct-GGUF',
                filename='Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf',
                local_dir='model')
"
# Then rename: mv model/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf model/murder-mystery.gguf
```

> **Tip**: `HF_TOKEN` is optional but avoids rate-limiting — create a free account at huggingface.co and generate a token.

```bash
cp .env.example .env
# Edit .env: set BACKEND=mlx (Apple Silicon) or BACKEND=llamacpp (GPU/CPU)
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

#### 1. Generate training data (~2700 examples via Claude) — can be skipped (already included)

```bash
cd training
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-train.txt   # or the cuda/rocm variant — just needs anthropic

ANTHROPIC_API_KEY=sk-ant-... python generate_data.py
# Saves to data/npc_actions.jsonl, data/interrogations.jsonl, data/mystery_setups.jsonl
# Resumes automatically if interrupted
```

#### 2. Install training dependencies (pick your hardware)

**Apple Silicon:**
```bash
pip install -r requirements-train.txt
```

**NVIDIA CUDA** (install matching PyTorch first):
```bash
# CUDA 12.4 example — see requirements-train-cuda.txt for other versions
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-train-cuda.txt
```

**AMD ROCm** — **Linux or WSL2 only** (PyTorch has no Windows ROCm wheels):
```bash
# ROCm 7.2 (current stable) — see requirements-train-rocm.txt for legacy 6.x versions
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm7.2
pip install -r requirements-train-rocm.txt
```

#### 3. Fine-tune

`train.py` auto-detects hardware. Override with `--backend` if needed.

**Apple Silicon:**
```bash
python train.py
# Default: Llama 3.1 8B 4-bit, batch=1, 5-min cooldown between epochs
# Checkpoint every 50 steps — crash-safe
# ~2.5 hours on M4 Air

python train.py --model mlx-community/Phi-3.5-mini-instruct-4bit   # faster / less RAM
python train.py --cooldown 0   # MacBook Pro / Mac Studio (active cooling)
```

**NVIDIA / AMD GPU:**
```bash
python train.py --backend cuda   # or --backend rocm
# Default: unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit, batch=2
# Requires ~6 GB VRAM; increase --batch-size on cards with more VRAM

python train.py --backend cuda --model unsloth/Phi-3.5-mini-instruct-bnb-4bit   # ~3 GB VRAM
python train.py --backend cuda --batch-size 4   # e.g. RTX 4090 / A100
```

#### 4. Deploy and run

**Apple Silicon** (MLX model → mlx-lm backend):
```bash
cp -r checkpoints/mlx-model ../llm-server/model/mlx-model
# Ensure llm-server/.env has BACKEND=mlx
cd ../llm-server && uvicorn server:app --host 127.0.0.1 --port 8000
```

**NVIDIA / AMD GPU** (export to GGUF → llama-cpp backend):
```bash
# Convert merged checkpoint to GGUF
python export_gguf.py
cp model-gguf/murder-mystery-q4_k_m.gguf ../llm-server/model/murder-mystery.gguf
# Set BACKEND=llamacpp in llm-server/.env
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

## Training backend overview

| Backend | Library | When to use |
|---------|---------|-------------|
| `mlx` (default on macOS/arm) | [`mlx-tune`](https://github.com/ARahim3/mlx-tune) | Apple Silicon — no CUDA/Triton required; runs natively on the M-series Neural Engine |
| `cuda` | [`unsloth`](https://github.com/unslothai/unsloth) + `trl` | NVIDIA GPUs (RTX, A100, H100 …) |
| `rocm` | `unsloth` + `trl` | AMD GPUs (RX 7900, MI300 …) via ROCm/HIP |

`mlx-tune` and `unsloth` share an identical `FastLanguageModel` / `SFTTrainer` API — `train.py` imports the right one automatically. `export_gguf.py` also works with either library since both expose the same `save_pretrained_gguf()` method.

The backend is selected automatically at startup (`auto` mode) or forced with `--backend <mlx|cuda|rocm>`.

