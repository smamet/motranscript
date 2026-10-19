---
name: setup
description: >-
  Install and run MoTranscript locally (Docker MySQL, uv, Node, sail up).
  Use when the user asks to set up, install, bootstrap, run, or launch this
  project for the first time, or when the local stack will not start.
---

# Set up MoTranscript locally

## Goal

Get the annotation UI running on the laptop: MySQL in Docker, FastAPI API, Vite web, background worker.

## Prerequisites

Confirm these are available before changing the project:

- Docker Desktop (or Docker Engine + Compose)
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+ and npm
- Python is provided by `uv` — do not create a separate venv by hand

## Steps

1. From the repository root, copy env defaults if `.env` is missing:

```bash
cp .env.example .env
```

2. Set a non-default `SECRET_KEY` in `.env` before any real use.

3. Start the stack:

```bash
./sail up
```

This starts MySQL on port 3307, runs migrations, builds the web UI, and starts API (8000), Vite (8010), and the worker.

4. Open http://localhost:8010

5. Sign in with the seeded admin, then change the password immediately:

- email: `admin@example.com`
- password: `admin`

## Optional extras

Ask the user before enabling these — they are not required for the UI:

| Need | Env / action |
| --- | --- |
| Hugging Face diarization / gated models | `HF_TOKEN` in `.env` |
| RunPod cloud ASR | `INFERENCE_BACKEND=runpod`, `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `PUBLIC_BASE_URL` |
| LoRA training | see [docs/training.md](../../../docs/training.md) |
| Lortograf LLM pass | `LORTOGRAF_USE_LLM=true` + `OPENAI_API_KEY` |

Local Mac ASR uses `INFERENCE_BACKEND=local` (default) and downloads Whisper weights on first job.

## Hard rules

- Do **not** SSH to any remote host.
- Do **not** import or restore production data.
- Do **not** commit `.env`, cookies, or anything under `secrets/` or `data/`.
- Do **not** invent one-off docker/mysql commands when `./sail up`, `./sail down`, `./sail status`, `./sail logs`, or `./sail backup` already cover the need.

## If something fails

1. `./sail status` and `./sail logs`
2. Confirm Docker is running and port 3307 / 8000 / 8010 are free
3. `uv sync` then `./sail up` again
4. Report the error; fix the project scripts rather than bypassing them
