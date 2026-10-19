"""Terminate the current RunPod pod."""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def terminate_self() -> None:
    pod_id = os.environ.get("RUNPOD_POD_ID")
    api_key = os.environ.get("RUNPOD_API_KEY")
    if not pod_id:
        log.warning("RUNPOD_POD_ID not set; skip terminate")
        return
    if not api_key:
        log.warning("RUNPOD_API_KEY not set; cannot terminate pod %s", pod_id)
        return
    try:
        import runpod

        runpod.api_key = api_key
        runpod.terminate_pod(pod_id)
        log.info("Terminated pod %s", pod_id)
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to terminate pod %s: %s", pod_id, exc)
