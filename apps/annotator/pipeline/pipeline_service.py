"""Shared diarize → ASR → merge pipeline used by local worker and RunPod."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from apps.annotator.config import get_settings
from apps.annotator.db.models import SegmentLang
from apps.annotator.pipeline.asr_engine import AsrSegment, AsrWord, get_asr_engine
from apps.annotator.pipeline.diarizer import DiarizationTurn, Diarizer
from apps.annotator.pipeline.segment_merger import MergedSegment, SegmentMerger

log = logging.getLogger(__name__)

PhaseCallback = Callable[[float, str], None]


@dataclass
class PipelineResult:
    segments: list[MergedSegment]
    pipeline_meta: dict
    model_name: str


class PipelineService:
    """CPU/GPU transcription pipeline without DB access."""

    def __init__(self, *, model_name: str | None = None) -> None:
        self.settings = get_settings()
        self.model_name = model_name or self.settings.whisper_model
        self.merger = SegmentMerger()

    def run(
        self,
        audio_path: Path,
        *,
        default_lang: SegmentLang = SegmentLang.mix,
        on_phase: PhaseCallback | None = None,
    ) -> PipelineResult:
        def phase(progress: float, message: str) -> None:
            if on_phase:
                on_phase(progress, message)

        phase(0.05, f"Loading ASR model ({self.model_name})…")
        asr = get_asr_engine(self.model_name)

        pipeline_meta: dict = {
            "diarization_status": "skipped",
            "diarization_error": None,
            "speaker_count": 1,
            "asr_detected_lang": None,
        }

        skip = self._diarization_skip_reason()
        if skip:
            pipeline_meta["diarization_status"] = "skipped"
            pipeline_meta["diarization_error"] = skip
            phase(0.15, "Transcribing with Whisper…")
            asr_segments, detected_lang = asr.transcribe(audio_path, default_lang=default_lang)
            pipeline_meta["asr_detected_lang"] = detected_lang
            phase(0.7, "Transcription complete")
            merged = self.merger.merge_asr_only(asr_segments)
        else:
            try:
                phase(0.12, "Speaker diarization (pyannote)…")
                diarizer = Diarizer(min_speakers=2)
                turns = diarizer.diarize(audio_path)
                blocks = self.merger.coalesce_speaker_turns(turns)
                pipeline_meta["diarization_status"] = "ok"
                pipeline_meta["speaker_count"] = len({t.speaker for t in turns})

                phase(0.22, f"Transcribing {len(blocks)} speaker block(s)…")
                block_segments = self._transcribe_speaker_blocks(
                    asr, audio_path, blocks, default_lang
                )
                pipeline_meta["asr_detected_lang"] = "fr"
                phase(0.82, "Merging speakers & language boundaries…")
                merged = self.merger.merge_from_speaker_blocks(blocks, block_segments)
                pipeline_meta["speaker_count"] = len({m.speaker for m in merged}) or 1
            except Exception as exc:
                log.exception("Diarization failed")
                pipeline_meta["diarization_status"] = "failed"
                pipeline_meta["diarization_error"] = str(exc)
                pipeline_meta["speaker_count"] = 1
                phase(0.15, "Diarization failed — full-file Whisper…")
                asr_segments, detected_lang = asr.transcribe(
                    audio_path, default_lang=default_lang
                )
                pipeline_meta["asr_detected_lang"] = detected_lang
                phase(0.7, "Transcription complete (single speaker fallback)")
                merged = self.merger.merge_asr_only(asr_segments)

        pipeline_meta["speaker_count"] = len({m.speaker for m in merged}) or 1
        return PipelineResult(
            segments=merged,
            pipeline_meta=pipeline_meta,
            model_name=self.model_name,
        )

    def _diarization_skip_reason(self) -> str | None:
        if not self.settings.enable_diarization:
            return "Diarization disabled — single speaker; language auto-split only"
        if not self.settings.hf_token:
            return (
                "No HF_TOKEN — all speech assigned to one speaker. "
                "Set HuggingFace token + uv sync --extra pipeline for multi-speaker"
            )
        try:
            import pyannote.audio  # noqa: F401
        except ImportError:
            return (
                "pyannote not installed — run: uv sync --extra pipeline "
                "(single speaker until then)"
            )
        return None

    def _transcribe_speaker_blocks(
        self,
        asr,
        audio_path: Path,
        blocks: list[DiarizationTurn],
        default_lang: SegmentLang,
    ) -> list[list[AsrSegment]]:
        import tempfile

        block_segments: list[list[AsrSegment]] = []
        with tempfile.TemporaryDirectory(prefix="motranscript_blocks_") as tmp:
            tmp_path = Path(tmp)
            for idx, block in enumerate(blocks):
                clip = tmp_path / f"block_{idx:04d}.wav"
                SegmentMerger.cut_segment_wav(
                    str(audio_path),
                    str(clip),
                    block.start,
                    block.end,
                )
                segments, _ = asr.transcribe(clip, default_lang=default_lang)
                block_segments.append(self._offset_asr_segments(segments, block.start))
        return block_segments

    @staticmethod
    def _offset_asr_segments(segments: list[AsrSegment], offset: float) -> list[AsrSegment]:
        offset_segments: list[AsrSegment] = []
        for seg in segments:
            words = [
                AsrWord(
                    start=word.start + offset,
                    end=word.end + offset,
                    text=word.text,
                    language=word.language,
                )
                for word in (seg.words or [])
            ]
            offset_segments.append(
                AsrSegment(
                    start=seg.start + offset,
                    end=seg.end + offset,
                    text=seg.text,
                    language=seg.language,
                    words=words,
                )
            )
        return offset_segments


def segments_to_dicts(segments: list[MergedSegment]) -> list[dict]:
    return [asdict(s) for s in segments]


def segments_from_dicts(rows: list[dict]) -> list[MergedSegment]:
    return [
        MergedSegment(
            start=float(r["start"]),
            end=float(r["end"]),
            text=str(r["text"]),
            speaker=str(r.get("speaker") or "SPEAKER_00"),
            lang=str(r.get("lang") or "mix"),
        )
        for r in rows
    ]
