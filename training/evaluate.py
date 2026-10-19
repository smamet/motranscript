"""Evaluate ASR models on the frozen test split."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from training.config import TrainingConfig
from training.dataset import DatasetBuilder
from training.metrics import metrics_by_language


class ModelEvaluator:
    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def transcribe_ct2(self, model_id: str, audio_paths: list[str]) -> list[str]:
        from faster_whisper import WhisperModel

        device = "cpu"
        compute_type = "int8"
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
            elif torch.backends.mps.is_available():
                device = "cpu"
        except ImportError:
            pass

        whisper = WhisperModel(model_id, device=device, compute_type=compute_type)
        hyps: list[str] = []
        for path in audio_paths:
            segments, _ = whisper.transcribe(path, beam_size=5, vad_filter=True)
            hyps.append(" ".join(seg.text.strip() for seg in segments).strip())
        return hyps

    def evaluate_rows(self, model_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        refs = [r["text"] for r in rows]
        langs = [r.get("lang", "mix") for r in rows]
        durations = [float(r.get("duration", 0)) for r in rows]
        paths = [r["audio"] for r in rows]
        hyps = self.transcribe_ct2(model_id, paths)
        per_lang = metrics_by_language(
            refs,
            hyps,
            langs,
            min_seconds=self.config.min_lang_test_seconds,
            durations=durations,
        )
        overall = metrics_by_language(refs, hyps, langs, min_seconds=0, durations=durations)
        flat = next(iter(overall.values())) if len(overall) == 1 else {}
        if len(overall) > 1:
            all_refs, all_hyps = refs, hyps
            from training.metrics import compute_wer_cer, compute_phonetic_cer

            flat = compute_wer_cer(all_refs, all_hyps)
            flat["phonetic_cer"] = compute_phonetic_cer(all_refs, all_hyps)
        return {"overall": flat, "per_language": per_lang, "model_id": model_id}

    def evaluate_export_dir(self, model_id: str, export_dir: Path | None = None) -> dict[str, Any]:
        builder = DatasetBuilder(self.config)
        rows = builder.load_jsonl_dir(export_dir)
        test_rows = [r for r in rows if r.get("split") == "test"]
        if not test_rows:
            prepared = builder.prepare_rows(rows)
            test_rows = [r for r in prepared if r.get("split") == "test"]
        return self.evaluate_rows(model_id, test_rows)

    def evaluate_hub_dataset(self, model_id: str, repo_id: str) -> dict[str, Any]:
        from datasets import load_dataset

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        dsd = load_dataset(repo_id, token=token)
        test = dsd["test"]
        rows = []
        for item in test:
            audio = item["audio"]
            path = audio["path"] if isinstance(audio, dict) else str(audio)
            rows.append(
                {
                    "audio": path,
                    "text": item["text"],
                    "lang": item.get("lang", "mix"),
                    "duration": float(item.get("duration", 0)),
                }
            )
        return self.evaluate_rows(model_id, rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate a CT2/faster-whisper model on frozen test")
    parser.add_argument("--model", required=True, help="Model id, e.g. Systran/faster-whisper-large-v3")
    parser.add_argument("--data", type=Path, default=TrainingConfig().export_dir)
    parser.add_argument("--dataset", help="Hub dataset repo (uses test split)")
    parser.add_argument("--out", type=Path, help="Write metrics JSON here")
    args = parser.parse_args()

    evaluator = ModelEvaluator()
    if args.dataset:
        metrics = evaluator.evaluate_hub_dataset(args.model, args.dataset)
    else:
        metrics = evaluator.evaluate_export_dir(args.model, args.data)
    text = json.dumps(metrics, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
