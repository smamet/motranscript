from dataclasses import dataclass
from pathlib import Path

from apps.annotator.pipeline.asr_engine import AsrSegment


@dataclass
class AlignedWord:
    start: float
    end: float
    text: str
    score: float | None = None


class Aligner:
    """Forced alignment via WhisperX wav2vec2 models."""

    FRENCH_ALIGN_MODEL = "jonatasgrosman/wav2vec2-large-xlsr-53-french"

    def __init__(self) -> None:
        self._models: dict[str, tuple] = {}

    def align(
        self,
        audio_path: Path,
        segments: list[AsrSegment],
        language: str | None,
    ) -> list[AlignedWord]:
        import gc

        import torch
        import whisperx

        lang = self._resolve_language(language, segments)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        audio = whisperx.load_audio(str(audio_path))

        whisper_segments = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in segments
        ]
        if not whisper_segments:
            return []

        align_model, metadata = whisperx.load_align_model(
            language_code=lang,
            device=device,
            model_name=self.FRENCH_ALIGN_MODEL if lang == "fr" else None,
        )
        result = whisperx.align(
            whisper_segments,
            align_model,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        del align_model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        words: list[AlignedWord] = []
        for seg in result.get("segments", []):
            for word in seg.get("words", []):
                if word.get("start") is None or word.get("end") is None:
                    continue
                words.append(
                    AlignedWord(
                        start=float(word["start"]),
                        end=float(word["end"]),
                        text=str(word.get("word", "")).strip(),
                        score=word.get("score"),
                    )
                )
        return words

    @staticmethod
    def _resolve_language(language: str | None, segments: list[AsrSegment]) -> str:
        if language in {"en", "fr", "de", "es", "it", "pt", "nl"}:
            return language
        langs = {s.language for s in segments if s.language}
        if "en" in langs and len(langs) == 1:
            return "en"
        if "fr" in langs and len(langs) == 1:
            return "fr"
        # Kreol/mix: French aligner is closest per plan
        return "fr"
