"""LoRA fine-tuning for Whisper."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from training.config import TrainingConfig
from training.dataset import DatasetBuilder


@dataclass
class TrainResult:
    adapter_dir: Path
    run_dir: Path


class LoRATrainer:
    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def _prepare_model(self):
        import torch
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import WhisperForConditionalGeneration

        model = WhisperForConditionalGeneration.from_pretrained(
            self.config.base_model,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        model.config.use_cache = False
        model.gradient_checkpointing_enable()

        lora = LoraConfig(
            r=self.config.lora_r,
            lora_alpha=self.config.lora_alpha,
            target_modules=list(self.config.lora_target_modules),
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.SEQ_2_SEQ_LM,
        )
        return get_peft_model(model, lora)

    def _build_dataset(self, export_dir: Path | None):
        from transformers import WhisperProcessor

        builder = DatasetBuilder(self.config)
        rows = builder.load_jsonl_dir(export_dir)
        dsd = builder.to_dataset_dict(rows)
        processor = WhisperProcessor.from_pretrained(self.config.base_model)

        def _map(batch):
            import librosa

            audios = []
            for audio in batch["audio"]:
                path = audio["path"] if isinstance(audio, dict) else audio
                y, _ = librosa.load(path, sr=16000, mono=True)
                audios.append(y)
            inputs = processor(audios, sampling_rate=16000, return_tensors="np")
            batch["input_features"] = inputs.input_features
            labels = processor.tokenizer(batch["text"], return_tensors="np").input_ids
            labels[labels == processor.tokenizer.pad_token_id] = -100
            batch["labels"] = labels
            return batch

        train_ds = dsd["train"].map(_map, batched=True, remove_columns=dsd["train"].column_names)
        dev_ds = dsd["dev"].map(_map, batched=True, remove_columns=dsd["dev"].column_names)
        return train_ds, dev_ds, processor

    def train(self, export_dir: Path | None = None) -> TrainResult:
        import torch
        from transformers import EarlyStoppingCallback, Seq2SeqTrainer, Seq2SeqTrainingArguments

        run_dir = self.config.output_dir / self.config.base_model.split("/")[-1]
        run_dir.mkdir(parents=True, exist_ok=True)
        adapter_dir = run_dir / "adapter"

        train_ds, dev_ds, processor = self._build_dataset(export_dir)
        model = self._prepare_model()

        args = Seq2SeqTrainingArguments(
            output_dir=str(run_dir),
            per_device_train_batch_size=self.config.per_device_batch_size,
            per_device_eval_batch_size=self.config.per_device_batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            warmup_ratio=self.config.warmup_ratio,
            num_train_epochs=self.config.num_train_epochs,
            max_steps=self.config.max_steps if self.config.max_steps > 0 else -1,
            eval_strategy="steps",
            eval_steps=50 if self.config.max_steps > 0 else 200,
            save_strategy="steps",
            save_steps=50 if self.config.max_steps > 0 else 200,
            load_best_model_at_end=self.config.max_steps <= 0,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            fp16=torch.cuda.is_available(),
            logging_steps=10,
            report_to="none",
            remove_unused_columns=False,
            label_names=["labels"],
            dataloader_num_workers=0,
        )

        trainer = Seq2SeqTrainer(
            model=model,
            args=args,
            train_dataset=train_ds,
            eval_dataset=dev_ds,
            processing_class=processor,
            callbacks=[EarlyStoppingCallback(early_stopping_patience=self.config.early_stopping_patience)],
        )
        trainer.train()
        model.save_pretrained(adapter_dir)
        processor.save_pretrained(adapter_dir)
        return TrainResult(adapter_dir=adapter_dir, run_dir=run_dir)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="LoRA fine-tune Whisper on exported JSONL")
    parser.add_argument("--base", default="openai/whisper-large-v3")
    parser.add_argument("--data", type=Path, default=TrainingConfig().export_dir)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--output-dir", type=Path, default=TrainingConfig().output_dir)
    args = parser.parse_args()

    cfg = TrainingConfig(
        base_model=args.base,
        max_steps=args.max_steps,
        output_dir=args.output_dir,
    )
    if args.max_steps > 0:
        cfg.num_train_epochs = 1.0
    result = LoRATrainer(cfg).train(args.data)
    print(f"Adapter saved to {result.adapter_dir}")


if __name__ == "__main__":
    main()
