"""Full training cycle: train, evaluate, quality gate, publish."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from training.config import TrainingConfig
from training.dataset import DatasetBuilder
from training.evaluate import ModelEvaluator
from training.metrics import gate_passes
from training.pod import terminate_self
from training.publish import ModelPublisher
from training.train_lora import LoRATrainer

log = logging.getLogger(__name__)


class TrainingCycle:
    def __init__(
        self,
        *,
        dataset_repo: str | None = None,
        output_repo: str,
        export_dir: Path | None = None,
        baseline_model: str = "Systran/faster-whisper-large-v3",
        baseline_metrics_path: Path | None = None,
        config: TrainingConfig | None = None,
    ) -> None:
        self.dataset_repo = dataset_repo
        self.output_repo = output_repo
        self.export_dir = export_dir
        self.baseline_model = baseline_model
        self.baseline_metrics_path = baseline_metrics_path
        self.config = config or TrainingConfig()
        self.work_dir = self.config.output_dir / "cycle"

    def run(self) -> dict:
        try:
            return self._run()
        finally:
            terminate_self()

    def _run(self) -> dict:
        builder = DatasetBuilder(self.config)
        if self.dataset_repo:
            export_dir = builder.materialize_hub(self.dataset_repo, self.work_dir / "export")
        else:
            export_dir = self.export_dir or self.config.export_dir

        evaluator = ModelEvaluator(self.config)
        baseline_metrics = self._load_baseline(evaluator, export_dir)
        log.info("Baseline metrics: %s", json.dumps(baseline_metrics, indent=2))

        train_result = LoRATrainer(self.config).train(export_dir)
        merged_eval_dir = self.work_dir / "merged_eval"
        merged_eval_dir.mkdir(parents=True, exist_ok=True)

        publisher = ModelPublisher(self.config.base_model)
        merged = merged_eval_dir / "merged"
        ct2 = merged_eval_dir / "ct2"
        publisher.merge_adapter(train_result.adapter_dir, merged)
        publisher.convert_ct2(merged, ct2)

        candidate_metrics = evaluator.evaluate_export_dir(str(ct2), export_dir)
        per_lang = candidate_metrics.get("per_language", {})
        base_per_lang = baseline_metrics.get("per_language", {})
        passed, reasons = gate_passes(per_lang, base_per_lang)

        result = {
            "published": False,
            "output_repo": self.output_repo,
            "baseline": baseline_metrics,
            "candidate": candidate_metrics,
            "gate_passed": passed,
            "gate_reasons": reasons,
        }

        if passed:
            repo = publisher.push_ct2(ct2, self.output_repo, candidate_metrics)
            result["published"] = True
            result["output_repo"] = repo
            log.info("Published %s", repo)
        else:
            log.warning("Quality gate failed: %s", reasons)

        report_path = self.work_dir / "cycle_report.json"
        report_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return result

    def _load_baseline(self, evaluator: ModelEvaluator, export_dir: Path | None) -> dict:
        if self.baseline_metrics_path and self.baseline_metrics_path.exists():
            return json.loads(self.baseline_metrics_path.read_text(encoding="utf-8"))
        return evaluator.evaluate_export_dir(self.baseline_model, export_dir)


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Train LoRA, gate on frozen test, publish CT2")
    parser.add_argument("--dataset", help="HF dataset repo id")
    parser.add_argument("--output-repo", required=True, help="HF model repo for CT2 output")
    parser.add_argument("--data", type=Path, help="Local export dir if not using --dataset")
    parser.add_argument("--baseline-metrics", type=Path, help="Precomputed baseline JSON")
    parser.add_argument("--base", default="openai/whisper-large-v3")
    args = parser.parse_args()

    cfg = TrainingConfig(base_model=args.base)
    cycle = TrainingCycle(
        dataset_repo=args.dataset,
        output_repo=args.output_repo,
        export_dir=args.data,
        baseline_metrics_path=args.baseline_metrics,
        config=cfg,
    )
    result = cycle.run()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
