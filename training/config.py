"""Shared training configuration."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TrainingConfig:
    base_model: str = "openai/whisper-large-v3"
    lora_r: int = 32
    lora_alpha: int = 64
    lora_target_modules: tuple[str, ...] = ("q_proj", "v_proj")
    learning_rate: float = 1e-4
    num_train_epochs: float = 5.0
    max_steps: int = -1
    per_device_batch_size: int = 4
    gradient_accumulation_steps: int = 8
    warmup_ratio: float = 0.05
    dev_fraction: float = 0.08
    dev_seed: int = 42
    min_test_seconds: float = 1200.0  # 20 min
    min_lang_test_seconds: float = 30.0
    early_stopping_patience: int = 3
    output_dir: Path = field(default_factory=lambda: Path("data/training_runs"))
    export_dir: Path = field(default_factory=lambda: Path("data/exports/all_validated"))
