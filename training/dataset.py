"""Build HF datasets from local exports and push/pull the Hub."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict, Audio

from training.config import TrainingConfig
from training.splits import SplitError, assign_dev_split, validate_test_split


class DatasetBuilder:
    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def load_jsonl_dir(self, export_dir: Path | None = None) -> list[dict[str, Any]]:
        root = export_dir or self.config.export_dir
        jsonl_path = root / "dataset.jsonl"
        if not jsonl_path.exists():
            raise FileNotFoundError(f"No dataset.jsonl under {root}")
        rows: list[dict[str, Any]] = []
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        for row in rows:
            rel = row.get("audio_path", "")
            row["audio"] = str((root / rel).resolve()) if rel else ""
        return rows

    def prepare_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with_dev = assign_dev_split(
            rows,
            fraction=self.config.dev_fraction,
            seed=self.config.dev_seed,
        )
        validate_test_split(with_dev, min_test_seconds=self.config.min_test_seconds)
        return with_dev

    def to_dataset_dict(self, rows: list[dict[str, Any]]) -> DatasetDict:
        prepared = self.prepare_rows(rows)
        ds = Dataset.from_list(
            [
                {
                    "audio": r["audio"],
                    "text": r["text"],
                    "lang": r.get("lang", "mix"),
                    "split": r.get("split", "train"),
                    "duration": float(r.get("duration", 0)),
                }
                for r in prepared
                if r.get("audio") and Path(r["audio"]).exists()
            ]
        )
        ds = ds.cast_column("audio", Audio(sampling_rate=16000))
        return DatasetDict(
            {
                "train": ds.filter(lambda x: x["split"] == "train"),
                "dev": ds.filter(lambda x: x["split"] == "dev"),
                "test": ds.filter(lambda x: x["split"] == "test"),
            }
        )

    def push(self, repo_id: str, export_dir: Path | None = None) -> DatasetDict:
        rows = self.load_jsonl_dir(export_dir)
        dsd = self.to_dataset_dict(rows)
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        dsd.push_to_hub(repo_id, private=True, token=token)
        return dsd

    def pull(self, repo_id: str) -> DatasetDict:
        from datasets import load_dataset

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        dsd = load_dataset(repo_id, token=token)
        if isinstance(dsd, Dataset):
            raise SplitError("Hub dataset must be a DatasetDict with train/dev/test splits.")
        test = dsd.get("test")
        if test is None or len(test) == 0:
            raise SplitError("Hub dataset has no test split.")
        rows = [
            {
                "audio": item["audio"]["path"] if isinstance(item["audio"], dict) else item["audio"],
                "text": item["text"],
                "lang": item.get("lang", "mix"),
                "split": "test",
                "duration": float(item.get("duration", 0)),
            }
            for item in test
        ]
        validate_test_split(rows, min_test_seconds=self.config.min_test_seconds)
        return dsd

    def materialize_hub(self, repo_id: str, dest: Path) -> Path:
        """Download Hub dataset splits into a local export folder (jsonl + wav)."""
        import shutil

        from datasets import load_dataset

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        dsd = load_dataset(repo_id, token=token)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        idx = 0
        for split_name in ("train", "dev", "test"):
            if split_name not in dsd:
                continue
            for item in dsd[split_name]:
                audio = item["audio"]
                src_path = Path(audio["path"] if isinstance(audio, dict) else audio)
                wav_name = f"segment_{idx}.wav"
                if src_path.exists():
                    shutil.copy2(src_path, dest / wav_name)
                rows.append(
                    {
                        "audio_path": wav_name,
                        "text": item["text"],
                        "lang": item.get("lang", "mix"),
                        "split": split_name,
                        "duration": float(item.get("duration", 0)),
                        "source_id": item.get("source_id", 0),
                        "segment_id": item.get("segment_id", idx),
                    }
                )
                idx += 1
        jsonl_path = dest / "dataset.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        validate_test_split(rows, min_test_seconds=self.config.min_test_seconds)
        return dest


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Push local export to Hugging Face dataset repo")
    parser.add_argument("--push", required=True, help="Hub repo id, e.g. user/motranscript-data")
    parser.add_argument("--data", type=Path, default=TrainingConfig().export_dir)
    args = parser.parse_args()
    builder = DatasetBuilder()
    dsd = builder.push(args.push, args.data)
    print(f"Pushed {args.push}: train={len(dsd['train'])}, dev={len(dsd['dev'])}, test={len(dsd['test'])}")


if __name__ == "__main__":
    main()
