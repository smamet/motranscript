"""Create a RunPod GPU pod, run training.cycle, watchdog-terminate."""

from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
DEFAULT_GPU = "NVIDIA A40"
WATCHDOG_SECONDS = 6 * 3600
POLL_SECONDS = 30


def _build_start_command(
    git_url: str,
    dataset: str,
    output_repo: str,
    branch: str = "main",
) -> str:
    return (
        f"bash -lc 'set -euo pipefail; "
        f"cd /workspace && "
        f"git clone --depth 1 --branch {branch} {git_url} motranscript && "
        f"cd motranscript && "
        f"pip install -q -e \".[training]\" && "
        f"python -m training.cycle --dataset {dataset} --output-repo {output_repo}'"
    )


def create_training_pod(
    *,
    dataset: str,
    output_repo: str,
    git_url: str,
    gpu_type: str = DEFAULT_GPU,
    image_name: str = DEFAULT_IMAGE,
    volume_id: str | None = None,
    branch: str = "main",
) -> str:
    import runpod

    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise RuntimeError("RUNPOD_API_KEY is required")
    runpod.api_key = api_key

    env: dict[str, str] = {}
    if os.environ.get("HF_TOKEN"):
        env["HF_TOKEN"] = os.environ["HF_TOKEN"]
    if api_key:
        env["RUNPOD_API_KEY"] = api_key

    pod = runpod.create_pod(
        name=f"motranscript-train-{int(time.time())}",
        image_name=image_name,
        gpu_type_id=gpu_type,
        cloud_type="COMMUNITY",
        support_public_ip=False,
        start_ssh=False,
        docker_args=_build_start_command(git_url, dataset, output_repo, branch),
        volume_in_gb=0,
        container_disk_in_gb=40,
        env=env,
        network_volume_id=volume_id,
    )
    pod_id = pod.get("id") if isinstance(pod, dict) else pod.id  # type: ignore[union-attr]
    log.info("Created pod %s", pod_id)
    return str(pod_id)


def watch_pod(pod_id: str, *, timeout_seconds: int = WATCHDOG_SECONDS) -> None:
    import runpod

    api_key = os.environ.get("RUNPOD_API_KEY")
    if not api_key:
        raise RuntimeError("RUNPOD_API_KEY is required")
    runpod.api_key = api_key

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        pod = runpod.get_pod(pod_id)
        status = pod.get("desiredStatus") or pod.get("status") if isinstance(pod, dict) else None
        log.info("Pod %s status: %s", pod_id, status)
        if status in ("EXITED", "COMPLETED", None):
            return
        time.sleep(POLL_SECONDS)

    log.warning("Watchdog: pod %s still running after %ds — terminating", pod_id, timeout_seconds)
    runpod.terminate_pod(pod_id)


def launch(
    *,
    dataset: str,
    output_repo: str,
    git_url: str,
    gpu_type: str = DEFAULT_GPU,
    volume_id: str | None = None,
    branch: str = "main",
    watch: bool = True,
) -> str:
    pod_id = create_training_pod(
        dataset=dataset,
        output_repo=output_repo,
        git_url=git_url,
        gpu_type=gpu_type,
        volume_id=volume_id,
        branch=branch,
    )
    if watch:
        watch_pod(pod_id)
    return pod_id


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Launch RunPod training pod via API")
    parser.add_argument("--dataset", required=True, help="HF dataset repo id")
    parser.add_argument("--output-repo", required=True, help="HF CT2 model repo id")
    parser.add_argument(
        "--git-url",
        default=os.environ.get("MOTRANSCRIPT_GIT_URL", ""),
        help="Public git URL to clone on the pod",
    )
    parser.add_argument("--branch", default="main")
    parser.add_argument("--gpu", default=DEFAULT_GPU)
    parser.add_argument("--volume-id", default=os.environ.get("RUNPOD_VOLUME_ID"))
    parser.add_argument("--no-watch", action="store_true")
    args = parser.parse_args()

    if not args.git_url:
        raise SystemExit("Set --git-url or MOTRANSCRIPT_GIT_URL to your motranscript repository.")

    pod_id = launch(
        dataset=args.dataset,
        output_repo=args.output_repo,
        git_url=args.git_url,
        gpu_type=args.gpu,
        volume_id=args.volume_id,
        branch=args.branch,
        watch=not args.no_watch,
    )
    print(f"Pod {pod_id}")


if __name__ == "__main__":
    main()
