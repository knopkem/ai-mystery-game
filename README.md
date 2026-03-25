# AI Murder Mystery

A **turn-based 2D murder mystery** game where NPCs are controlled by a locally-running fine-tuned LLM. Each playthrough is unique — the killer, motive, evidence placement, and NPC behaviors are all dynamically generated and driven by the model.

## Concept

The player is a detective investigating a murder in a Victorian mansion. 5 suspects roam 5 rooms. Each game turn, NPCs autonomously decide to move, hide/destroy evidence, coordinate alibis, or plant false clues — all driven by a local fine-tuned language model. The player must interrogate suspects (whose responses are also LLM-generated) and accuse the correct killer before 15 turns pass.

## Stack

| Component | Technology |
|-----------|-----------|
| Game Engine | Godot 4.x (GDScript) |
| LLM Server | Python + FastAPI |
| Base Model | Qwen2.5-3B (mlx-community 4-bit) |
| Fine-tuning | mlx-tune (Unsloth-compatible, Apple Silicon native) |
| Inference | mlx-lm (MLX native) / llama-cpp-python (GGUF fallback) |
| Communication | HTTP REST (localhost:8000) |

**Target hardware**: MacBook M4, 16GB RAM (~2-3GB model, ~1-2GB Godot)

## Project Structure

```
ai-game/
├── llm-server/          # Python FastAPI inference server
│   ├── server.py        # API endpoints (mlx-lm or llama-cpp backend)
│   ├── prompts.py       # Prompt templates
│   ├── schemas.py       # Pydantic request/response models
│   ├── fallback.py      # Rule-based NPC fallbacks
│   ├── .env.example     # Config template (BACKEND, model paths)
│   └── model/           # Model files (gitignored)
├── training/            # mlx-tune fine-tuning pipeline (Apple Silicon)
│   ├── generate_data.py # Synthetic data generation via cloud LLM
│   ├── train.py         # mlx-tune SFT with LoRA — no CUDA required
│   ├── export_gguf.py   # Optional GGUF export for cross-platform deploy
│   ├── evaluate.py      # Quality evaluation (mlx or llamacpp backend)
│   └── data/            # JSONL training data
├── godot-game/          # Godot 4.x game project
│   ├── scenes/          # Game scenes (rooms, UI, NPCs)
│   ├── scripts/         # GDScript source files
│   └── assets/          # Minimal art assets
└── docs/
    └── game-design.md   # Full game design document
```

## Getting Started

### 1. Set up the LLM server

```bash
cd llm-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # default: BACKEND=mlx
```

**First time — run the training pipeline** to produce the fine-tuned model:
```bash
cd ../training
pip install -r requirements-train.txt   # installs mlx-tune, mlx, mlx-lm

OPENAI_API_KEY=sk-... python generate_data.py   # generate ~2700 synthetic examples
python train.py                                  # fine-tune on Apple Silicon (no CUDA needed)
# Saves model to: checkpoints/mlx-model/

cp -r checkpoints/mlx-model ../llm-server/model/mlx-model
```

> **Why mlx-tune instead of Unsloth?**
> Unsloth requires Triton which is CUDA-only and unavailable on macOS.
> [`mlx-tune`](https://github.com/ARahim3/mlx-tune) is a community-built drop-in replacement
> with an identical API (`FastLanguageModel`, `SFTTrainer`) that runs natively on Apple Silicon.
> Inference uses [`mlx-lm`](https://github.com/ml-explore/mlx-lm) — also native MLX, no llama.cpp needed.
> GGUF export via `export_gguf.py` is available if you ever want to deploy cross-platform.

**Start the server**:
```bash
cd ../llm-server
uvicorn server:app --host 127.0.0.1 --port 8000
```

### 2. Open the Godot project

Open Godot 4.x, import `godot-game/project.godot`, and run.

## Gameplay

- **Objective**: Identify the killer before 15 turns expire
- **Turn structure**:
  1. **Player Phase** (2 actions): Move, Examine evidence, Interrogate suspect, Accuse, Review notes
  2. **NPC Phase**: Each suspect autonomously acts (driven by LLM)
  3. **Event Phase**: Random mansion events
- **Win**: Correctly accuse killer + state correct motive
- **Lose**: Wrong accusation, or killer destroys all critical evidence, or 15 turns pass

## NPC Action Schema

NPCs output structured JSON actions:
```json
{
  "action": "hide_evidence",
  "target": "kitchen_knife",
  "secondary_target": null,
  "internal_thought": "The detective is getting too close. I need to move the knife."
}
```

Interrogation responses:
```json
{
  "dialogue": "I was in the library all evening, I tell you.",
  "lie": true,
  "emotion": "defensive",
  "internal_thought": "I can't let them know I was in the kitchen."
}
```
