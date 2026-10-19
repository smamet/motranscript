"""Merge LoRA, convert to CTranslate2, push to Hugging Face."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class ModelPublisher:
    def __init__(self, base_model: str = "openai/whisper-large-v3") -> None:
        self.base_model = base_model

    def merge_adapter(self, adapter_dir: Path, merged_dir: Path) -> Path:
        import torch
        from peft import PeftModel
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        merged_dir.mkdir(parents=True, exist_ok=True)
        base = WhisperForConditionalGeneration.from_pretrained(
            self.base_model,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        model = PeftModel.from_pretrained(base, str(adapter_dir))
        model = model.merge_and_unload()
        model.save_pretrained(merged_dir)
        processor = WhisperProcessor.from_pretrained(adapter_dir)
        processor.save_pretrained(merged_dir)
        return merged_dir

    def convert_ct2(self, merged_dir: Path, ct2_dir: Path) -> Path:
        if ct2_dir.exists():
            shutil.rmtree(ct2_dir)
        ct2_dir.mkdir(parents=True)
        cmd = [
            "ct2-transformers-converter",
            "--model",
            str(merged_dir),
            "--output_dir",
            str(ct2_dir),
            "--copy_files",
            "tokenizer.json",
            "preprocessor_config.json",
            "--quantization",
            "float16",
        ]
        subprocess.run(cmd, check=True)
        return ct2_dir

    def push_ct2(
        self,
        ct2_dir: Path,
        repo_id: str,
        metrics: dict[str, Any],
        *,
        private: bool = True,
    ) -> str:
        from huggingface_hub import HfApi

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        api = HfApi(token=token)
        api.create_repo(repo_id, repo_type="model", private=private, exist_ok=True)
        api.upload_folder(folder_path=str(ct2_dir), repo_id=repo_id, repo_type="model")
        readme = self._readme(repo_id, metrics)
        api.upload_file(
            path_or_fileobj=readme.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="model",
        )
        return repo_id

    def publish(
        self,
        adapter_dir: Path,
        repo_id: str,
        metrics: dict[str, Any],
        work_dir: Path,
    ) -> str:
        merged = work_dir / "merged"
        ct2 = work_dir / "ct2"
        self.merge_adapter(adapter_dir, merged)
        self.convert_ct2(merged, ct2)
        return self.push_ct2(ct2, repo_id, metrics)

    @staticmethod
    def _readme(repo_id: str, metrics: dict[str, Any]) -> str:
        body = json.dumps(metrics, indent=2, ensure_ascii=False)
        return f"""---
language:
- kreol
- fr
- en
library_name: ctranslate2
tags:
- whisper
- asr
- motranscript
---

# {repo_id}

Fine-tuned Whisper (CTranslate2) for Mauritian Creole / French / English code-switching.

## Metrics (frozen test set)

```json
{body}
```
"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Merge LoRA and publish CT2 model to Hub")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--repo", required=True, help="Output Hub repo id")
    parser.add_argument("--base", default="openai/whisper-large-v3")
    parser.add_argument("--metrics", type=Path, help="JSON metrics file")
    parser.add_argument("--work-dir", type=Path, default=Path("data/training_runs/publish"))
    args = parser.parse_args()

    metrics: dict[str, Any] = {}
    if args.metrics and args.metrics.exists():
        metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    publisher = ModelPublisher(base_model=args.base)
    repo = publisher.publish(args.adapter, args.repo, metrics, args.work_dir)
    print(f"Published {repo}")


if __name__ == "__main__":
    main()
