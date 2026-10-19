"""Local vs RunPod inference backends for TranscriptionJob."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlencode

import httpx

from apps.annotator.config import get_settings
from apps.annotator.db.models import SegmentLang
from apps.annotator.pipeline.pipeline_service import (
    PhaseCallback,
    PipelineResult,
    PipelineService,
    segments_from_dicts,
)

log = logging.getLogger(__name__)


class InferenceBackend(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        default_lang: SegmentLang,
        source_id: int,
        on_phase: PhaseCallback | None = None,
    ) -> PipelineResult:
        raise NotImplementedError


class LocalInferenceBackend(InferenceBackend):
    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        default_lang: SegmentLang,
        source_id: int,
        on_phase: PhaseCallback | None = None,
    ) -> PipelineResult:
        return PipelineService(model_name=model_name).run(
            audio_path,
            default_lang=default_lang,
            on_phase=on_phase,
        )


class RunPodInferenceBackend(InferenceBackend):
    """Submit async /run job; RunPod worker downloads audio via signed VPS URL."""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.runpod_api_key or not self.settings.runpod_endpoint_id:
            raise RuntimeError(
                "RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID required for runpod backend"
            )
        if not self.settings.public_base_url:
            raise RuntimeError(
                "PUBLIC_BASE_URL required so RunPod can fetch audio from the VPS"
            )

    def transcribe(
        self,
        audio_path: Path,
        *,
        model_name: str,
        default_lang: SegmentLang,
        source_id: int,
        on_phase: PhaseCallback | None = None,
    ) -> PipelineResult:
        def phase(progress: float, message: str) -> None:
            if on_phase:
                on_phase(progress, message)

        audio_url = sign_audio_url(source_id, ttl_seconds=7200)
        phase(0.05, "Submitting job to RunPod Serverless…")
        payload = {
            "input": {
                "audio_url": audio_url,
                "model_name": model_name,
                "default_lang": default_lang.value,
                "hf_token": self.settings.hf_token or None,
                "enable_diarization": self.settings.enable_diarization,
            }
        }
        headers = {"Authorization": f"Bearer {self.settings.runpod_api_key}"}
        base = f"https://api.runpod.ai/v2/{self.settings.runpod_endpoint_id}"

        with httpx.Client(timeout=60.0) as client:
            submit = client.post(f"{base}/run", json=payload, headers=headers)
            submit.raise_for_status()
            job_id = submit.json()["id"]
            phase(0.1, f"RunPod job {job_id} queued…")

            deadline = time.time() + self.settings.runpod_job_timeout_sec
            while time.time() < deadline:
                status_resp = client.get(f"{base}/status/{job_id}", headers=headers)
                status_resp.raise_for_status()
                body = status_resp.json()
                status = body.get("status")
                if status == "COMPLETED":
                    output = body.get("output") or {}
                    if isinstance(output, list):
                        output = output[0] if output else {}
                    if output.get("error"):
                        raise RuntimeError(f"RunPod job failed: {output['error']}")
                    segments = segments_from_dicts(output.get("segments") or [])
                    return PipelineResult(
                        segments=segments,
                        pipeline_meta=output.get("pipeline_meta") or {},
                        model_name=output.get("model_name") or model_name,
                    )
                if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                    raise RuntimeError(f"RunPod job {status}: {body}")
                phase(0.3, f"RunPod {status.lower()}…")
                time.sleep(5)

        raise TimeoutError(
            f"RunPod job {job_id} did not finish within "
            f"{self.settings.runpod_job_timeout_sec}s"
        )


def get_inference_backend() -> InferenceBackend:
    settings = get_settings()
    backend = (settings.inference_backend or "local").lower().strip()
    if backend == "runpod":
        return RunPodInferenceBackend()
    if backend == "local":
        return LocalInferenceBackend()
    raise ValueError(f"Unknown INFERENCE_BACKEND={backend!r} (use local|runpod)")


def sign_audio_url(source_id: int, *, ttl_seconds: int = 7200) -> str:
    settings = get_settings()
    exp = int(time.time()) + ttl_seconds
    msg = f"{source_id}:{exp}".encode()
    sig = hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()
    query = urlencode({"exp": exp, "sig": sig})
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/internal/audio/{source_id}?{query}"


def verify_audio_signature(source_id: int, exp: int, sig: str) -> bool:
    settings = get_settings()
    if exp < int(time.time()):
        return False
    msg = f"{source_id}:{exp}".encode()
    expected = hmac.new(settings.secret_key.encode(), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
