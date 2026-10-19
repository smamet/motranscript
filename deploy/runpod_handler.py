"""RunPod Serverless handler: download WAV → PipelineService → segments JSON."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path


def _prepend_nvidia_lib_path() -> None:
    """CTranslate2 needs pip nvidia-cudnn libs on LD_LIBRARY_PATH before it dlopens."""
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return
    extras = [
        os.path.join(nvidia.cudnn.__path__[0], "lib"),
        os.path.join(nvidia.cublas.__path__[0], "lib"),
    ]
    current = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join(
        [p for p in extras if os.path.isdir(p)] + ([current] if current else [])
    )


_prepend_nvidia_lib_path()

import httpx
import runpod

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("motranscript.handler")


def _apply_job_env(job_input: dict) -> None:
    from apps.annotator.config import get_settings

    if job_input.get("hf_token"):
        os.environ["HF_TOKEN"] = str(job_input["hf_token"])
    if "enable_diarization" in job_input:
        os.environ["ENABLE_DIARIZATION"] = (
            "true" if job_input["enable_diarization"] else "false"
        )
    if job_input.get("model_name"):
        os.environ["WHISPER_MODEL"] = str(job_input["model_name"])
    get_settings.cache_clear()


def _download(url: str, dest: Path) -> None:
    with (
        httpx.Client(timeout=600.0, follow_redirects=True) as client,
        client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes(1024 * 1024):
                f.write(chunk)


def handler(job: dict) -> dict:
    job_input = job.get("input") or {}
    audio_url = job_input.get("audio_url")
    if not audio_url:
        return {"error": "audio_url is required"}

    _apply_job_env(job_input)

    from apps.annotator.db.models import SegmentLang
    from apps.annotator.pipeline.pipeline_service import PipelineService, segments_to_dicts

    model_name = job_input.get("model_name") or os.environ.get(
        "WHISPER_MODEL", "Systran/faster-whisper-large-v3"
    )
    lang_raw = (job_input.get("default_lang") or "mix").lower()
    try:
        default_lang = SegmentLang(lang_raw)
    except ValueError:
        default_lang = SegmentLang.mix

    with tempfile.TemporaryDirectory(prefix="rp_asr_") as tmp:
        wav_path = Path(tmp) / "audio.wav"
        log.info("Downloading audio…")
        try:
            _download(audio_url, wav_path)
        except Exception as exc:
            log.exception("Download failed")
            return {"error": f"download failed: {exc}"}

        log.info("Running pipeline model=%s lang=%s", model_name, default_lang.value)
        try:
            result = PipelineService(model_name=model_name).run(
                wav_path, default_lang=default_lang
            )
        except Exception as exc:
            log.exception("Pipeline failed")
            return {"error": f"pipeline failed: {exc}"}

        return {
            "segments": segments_to_dicts(result.segments),
            "pipeline_meta": result.pipeline_meta,
            "model_name": result.model_name,
        }


runpod.serverless.start({"handler": handler})
