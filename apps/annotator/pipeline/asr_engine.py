"""Kreol-aware ASR via faster-whisper."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from apps.annotator.config import get_settings
from apps.annotator.db.models import SegmentLang
from apps.annotator.pipeline.text_cleanup import collapse_repeated_tokens, fix_apostrophe_spacing, is_whisper_hallucination

KREOL_INITIAL_PROMPT = (
    "Transcription en kreol morisien, francais et anglais. "
    "Mo, ou, nou, ki, pa, manze, fer, kone, depi, bann, zot, seki, eski, pme."
)


@dataclass
class AsrWord:
    start: float
    end: float
    text: str
    language: str | None = None


@dataclass
class AsrSegment:
    start: float
    end: float
    text: str
    language: str | None
    words: list[AsrWord]


class AsrEngine:
    """CTranslate2 Whisper inference via faster-whisper."""

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.whisper_model
        self._model: WhisperModel | None = None

    @property
    def model(self) -> WhisperModel:
        if self._model is None:
            settings = get_settings()
            device = settings.whisper_device
            if device == "auto":
                device = "cpu"
                try:
                    import torch

                    if torch.cuda.is_available():
                        device = "cuda"
                except ImportError:
                    pass
            compute_type = settings.whisper_compute_type
            if device == "cpu" and compute_type == "float16":
                compute_type = "int8"
            self._model = WhisperModel(
                self.model_name,
                device=device,
                compute_type=compute_type,
                download_root=str(settings.model_cache_dir),
            )
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        *,
        default_lang: SegmentLang = SegmentLang.mix,
    ) -> tuple[list[AsrSegment], str | None]:
        use_kreol_prompt = default_lang in (SegmentLang.kreol, SegmentLang.mix)
        segments_iter, info = self.model.transcribe(
            str(audio_path),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            initial_prompt=KREOL_INITIAL_PROMPT if use_kreol_prompt else None,
            condition_on_previous_text=not use_kreol_prompt,
            repetition_penalty=1.12,
            no_repeat_ngram_size=3,
            compression_ratio_threshold=2.0,
            log_prob_threshold=-0.9,
            hallucination_silence_threshold=2.0,
        )
        segments: list[AsrSegment] = []
        for seg in segments_iter:
            cleaned = fix_apostrophe_spacing(collapse_repeated_tokens(seg.text.strip()))
            if is_whisper_hallucination(cleaned, seg.end - seg.start):
                continue
            words = [
                AsrWord(
                    start=w.start,
                    end=w.end,
                    text=w.word.strip(),
                    language=getattr(w, "language", None),
                )
                for w in (seg.words or [])
            ]
            if words:
                words = _collapse_word_repeats(words)
            segments.append(
                AsrSegment(
                    start=seg.start,
                    end=seg.end,
                    text=cleaned,
                    language=getattr(seg, "language", None) or info.language,
                    words=words,
                )
            )
        return segments, info.language


def _collapse_word_repeats(words: list[AsrWord], max_consecutive: int = 2) -> list[AsrWord]:
    """Drop excess consecutive duplicate words from word timestamps."""
    if not words:
        return words
    out: list[AsrWord] = []
    prev_key: str | None = None
    run = 0
    for word in words:
        key = word.text.lower().strip(".,;:!?\"'")
        if key and key == prev_key:
            run += 1
            if run <= max_consecutive:
                out.append(word)
        else:
            prev_key = key or prev_key
            run = 1
            out.append(word)
    return out


@lru_cache(maxsize=1)
def get_asr_engine(model_name: str) -> AsrEngine:
    return AsrEngine(model_name=model_name)
