from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from apps.annotator.config import get_settings


@dataclass
class DiarizationTurn:
    start: float
    end: float
    speaker: str


def _apply_hf_token(token: str | None) -> None:
    if not token:
        return
    os.environ["HF_TOKEN"] = token
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)


def _patch_hf_hub_download() -> None:
    """pyannote 3.x still passes use_auth_token=; huggingface_hub 1.x only accepts token=."""
    import huggingface_hub as hub

    orig = hub.hf_hub_download
    if getattr(orig, "_motranscript_token_compat", False):
        return

    def _download(*args, **kwargs):
        if "use_auth_token" in kwargs:
            auth = kwargs.pop("use_auth_token")
            kwargs.setdefault("token", auth)
        return orig(*args, **kwargs)

    _download._motranscript_token_compat = True  # type: ignore[attr-defined]
    hub.hf_hub_download = _download
    try:
        import pyannote.audio.core.pipeline as pyannote_pipeline

        pyannote_pipeline.hf_hub_download = _download
    except ImportError:
        pass


class Diarizer:
    """Speaker diarization via pyannote.audio 3.x."""

    def __init__(self, *, min_speakers: int | None = None) -> None:
        self._pipeline = None
        self.min_speakers = min_speakers

    @property
    def pipeline(self):
        if self._pipeline is None:
            import torch

            _apply_hf_token(get_settings().hf_token or None)
            _patch_hf_hub_download()
            from pyannote.audio import Pipeline

            # PyTorch 2.6+ defaults weights_only=True; pyannote checkpoints need False
            _orig_load = torch.load

            def _load_compat(*args, **kwargs):
                kwargs["weights_only"] = False
                return _orig_load(*args, **kwargs)

            torch.load = _load_compat  # type: ignore[assignment]
            try:
                self._pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                )
            finally:
                torch.load = _orig_load  # type: ignore[assignment]

            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self._pipeline.to(device)
        return self._pipeline

    def diarize(self, audio_path: Path) -> list[DiarizationTurn]:
        kwargs: dict = {}
        if self.min_speakers is not None:
            kwargs["min_speakers"] = self.min_speakers
        diarization = self.pipeline(str(audio_path), **kwargs)
        turns: list[DiarizationTurn] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(
                DiarizationTurn(start=turn.start, end=turn.end, speaker=str(speaker))
            )
        return sorted(turns, key=lambda t: t.start)
