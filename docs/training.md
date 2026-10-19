# LoRA training (Part 2)

## Accounts and keys

### Hugging Face (fine-grained token `motranscript`)

Enable only:

- Read contents of your repos
- Read contents of public gated repos you can access
- Write contents/settings of your repos

Put in `.env`:

```
HF_TOKEN=hf_...
```

Private repos:

- `YOURUSER/motranscript-data` (dataset)
- `YOURUSER/creole-asr-vN` (CT2 models)

### RunPod

1. Create account at [runpod.io](https://www.runpod.io/) and add **$20–25** credit.
2. Create an API key → `.env`:

```
RUNPOD_API_KEY=rpa_...
MOTRANSCRIPT_GIT_URL=https://github.com/YOURUSER/motranscript.git
# optional:
# RUNPOD_VOLUME_ID=...
```

Do **not** use the RunPod console for day-to-day training. Use `launch_runpod` from your Mac.

## Annotation workflow

1. Validate segments in the editor.
2. Pick 30–60 min of best audio → **Mark frozen test** on that source (never train on it).
3. When you have ~10 h validated → **Export all validated** on the Sources page.
4. Push dataset to Hub:

```bash
uv sync --extra training
python -m training.dataset --push YOURUSER/motranscript-data --data data/exports/all_validated
```

5. Baseline metrics (free, local stock model):

```bash
python -m training.evaluate --model Systran/faster-whisper-large-v3 --data data/exports/all_validated --out data/baseline_metrics.json
```

## Mac dry-run (before paying)

```bash
uv sync --extra training --extra pipeline
python -m training.train_lora --base openai/whisper-tiny --max-steps 20 --data data/exports/all_validated
```

## Paid training (RunPod pod API)

```bash
python -m training.launch_runpod \
  --dataset YOURUSER/motranscript-data \
  --output-repo YOURUSER/creole-asr-v1 \
  --git-url "$MOTRANSCRIPT_GIT_URL"
```

This creates a Community **A40** pod, runs `training.cycle`, and terminates the pod when done. A **6 h watchdog** kills forgotten pods.

Inside the pod, `training.cycle`:

1. Pulls dataset from Hub
2. LoRA fine-tunes `openai/whisper-large-v3` (full retrain, not incremental)
3. Evaluates on frozen test vs baseline
4. If WER **and** CER improve per language → merge LoRA → CT2 → push `creole-asr-vN`
5. Calls `terminate_pod` in `finally`

Cost: ~**$1–2** for ~3 h on A40.

## Activate the new model

1. Sources page → **Register & activate** with name `creole-asr-v1` and HF repo id.
2. Restart the worker: `uv run python -m apps.annotator.worker`
3. Next ingest uses the fine-tuned CT2 model.

## Local cycle (no RunPod)

If you already have a GPU machine:

```bash
python -m training.cycle \
  --dataset YOURUSER/motranscript-data \
  --output-repo YOURUSER/creole-asr-v1 \
  --baseline-metrics data/baseline_metrics.json
```

## Do not

- Leave a pod running overnight (console or API)
- Train without a frozen test split
- Use the Mac for `whisper-large-v3` LoRA (use tiny dry-run only)

Serverless ASR and VPS deployment: see [deploy.md](deploy.md). Global flow: [architecture.md](architecture.md).
