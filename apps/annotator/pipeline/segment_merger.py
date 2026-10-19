import subprocess
import wave
from dataclasses import dataclass

from apps.annotator.pipeline.aligner import AlignedWord
from apps.annotator.pipeline.asr_engine import AsrSegment
from apps.annotator.pipeline.diarizer import DiarizationTurn
from apps.annotator.pipeline.lang_detector import classify_word, resolve_segment_lang
from apps.annotator.pipeline.text_cleanup import is_whisper_hallucination, join_asr_words


@dataclass
class MergedSegment:
    start: float
    end: float
    text: str
    speaker: str
    lang: str


@dataclass
class _LabeledWord:
    start: float
    end: float
    text: str
    speaker: str
    lang: str


class SegmentMerger:
    MIN_DURATION = 1.5  # allow short language-boundary chunks
    MAX_DURATION = 10.0
    # Soft merge target for ASR-only path when no lang/speaker split
    PREFERRED_MIN_DURATION = 5.0

    SPEAKER_COLORS = ["#6366f1", "#22c55e", "#f97316", "#ec4899", "#14b8a6", "#eab308"]

    @staticmethod
    def filter_hallucinations(segments: list[MergedSegment]) -> list[MergedSegment]:
        """Drop Whisper noise/outro hallucinations (e.g. 'Thank you for watching!')."""
        return [
            seg
            for seg in segments
            if not is_whisper_hallucination(seg.text, seg.end - seg.start)
        ]

    def merge_asr_only(self, segments: list[AsrSegment]) -> list[MergedSegment]:
        labeled = self._label_from_asr(segments, speaker="SPEAKER_00")
        if labeled:
            return self.filter_hallucinations(self._merge_labeled_words(labeled))
        return self.filter_hallucinations(self._merge_asr_segments_legacy(segments))

    def merge_with_diarization(
        self,
        words: list[AlignedWord],
        turns: list[DiarizationTurn],
        fallback_segments: list[AsrSegment],
    ) -> list[MergedSegment]:
        if not words:
            return self.merge_asr_only(fallback_segments)

        labeled: list[_LabeledWord] = []
        for word in words:
            if not word.text:
                continue
            speaker = self._speaker_at(turns, word.start, word.end)
            labeled.append(
                _LabeledWord(
                    start=word.start,
                    end=word.end,
                    text=word.text,
                    speaker=speaker,
                    lang=classify_word(word.text),
                )
            )
        return self.filter_hallucinations(self._merge_labeled_words(labeled))

    def merge_from_speaker_blocks(
        self,
        blocks: list[DiarizationTurn],
        block_segments: list[list[AsrSegment]],
    ) -> list[MergedSegment]:
        """Merge per-speaker ASR runs (speaker already known per block)."""
        labeled: list[_LabeledWord] = []
        for block, segments in zip(blocks, block_segments):
            # Segments are already time-offset in TranscriptionJob._offset_asr_segments
            labeled.extend(self._label_from_asr(segments, speaker=block.speaker))
        return self.filter_hallucinations(self._merge_labeled_words(labeled))

    @staticmethod
    def coalesce_speaker_turns(
        turns: list[DiarizationTurn],
        *,
        gap_threshold: float = 0.5,
    ) -> list[DiarizationTurn]:
        """Merge consecutive same-speaker diarization turns into transcription blocks."""
        if not turns:
            return []
        ordered = sorted(turns, key=lambda t: (t.start, t.end))
        merged: list[DiarizationTurn] = [ordered[0]]
        for turn in ordered[1:]:
            last = merged[-1]
            if turn.speaker == last.speaker and turn.start - last.end <= gap_threshold:
                merged[-1] = DiarizationTurn(last.start, max(last.end, turn.end), last.speaker)
            else:
                merged.append(turn)
        return merged

    def _label_from_asr(
        self,
        segments: list[AsrSegment],
        speaker: str,
        *,
        time_offset: float = 0.0,
    ) -> list[_LabeledWord]:
        labeled: list[_LabeledWord] = []
        for seg in segments:
            if seg.words:
                for word in seg.words:
                    if not word.text:
                        continue
                    labeled.append(
                        _LabeledWord(
                            start=word.start + time_offset,
                            end=word.end + time_offset,
                            text=word.text,
                            speaker=speaker,
                            lang=classify_word(word.text),
                        )
                    )
            elif seg.text.strip():
                for token in seg.text.split():
                    labeled.append(
                        _LabeledWord(
                            start=seg.start + time_offset,
                            end=seg.end + time_offset,
                            text=token,
                            speaker=speaker,
                            lang=classify_word(token),
                        )
                    )
        return labeled

    def _merge_labeled_words(self, labeled: list[_LabeledWord]) -> list[MergedSegment]:
        merged: list[MergedSegment] = []
        current_speaker: str | None = None
        chunk_lang: str | None = None
        chunk_words: list[str] = []
        chunk_start: float | None = None
        chunk_end: float | None = None

        def flush() -> None:
            nonlocal chunk_lang, chunk_start, chunk_end, chunk_words, current_speaker
            if not chunk_words or chunk_start is None or chunk_end is None or not current_speaker:
                return
            text = join_asr_words(chunk_words)
            if not text:
                return
            lang = resolve_segment_lang(chunk_words, fallback=chunk_lang or "mix")
            merged.extend(
                self._segment_by_duration(
                    start=chunk_start,
                    end=chunk_end,
                    text=text,
                    speaker=current_speaker,
                    lang=lang,
                )
            )
            chunk_words = []
            chunk_start = None
            chunk_end = None
            chunk_lang = None

        for word in labeled:
            # Split on speaker change or max duration — not on fr/kreol word tags
            # (Whisper French output causes false lang splits within one utterance).
            split = False
            if current_speaker and word.speaker != current_speaker:
                split = True

            if split:
                flush()

            current_speaker = word.speaker
            if chunk_start is None:
                chunk_start = word.start
            chunk_end = word.end
            chunk_words.append(word.text)
            if word.lang in {"kreol", "fr"}:
                if chunk_lang is None:
                    chunk_lang = word.lang
                elif chunk_lang != word.lang and word.lang != "unknown":
                    # keep first dominant signal; resolve_segment_lang will mark mix
                    pass

            if chunk_start is not None and chunk_end is not None and chunk_end - chunk_start >= self.MAX_DURATION:
                flush()
                current_speaker = word.speaker

        flush()
        return merged

    def _segment_by_duration(
        self,
        start: float,
        end: float,
        text: str,
        speaker: str,
        lang: str,
    ) -> list[MergedSegment]:
        duration = end - start
        if duration <= self.MAX_DURATION:
            return [MergedSegment(start=start, end=end, text=text, speaker=speaker, lang=lang)]
        mid = start + self.MAX_DURATION
        return [MergedSegment(start=start, end=mid, text=text, speaker=speaker, lang=lang)]

    def _merge_asr_segments_legacy(self, segments: list[AsrSegment]) -> list[MergedSegment]:
        """Fallback when word timestamps are unavailable."""
        merged: list[MergedSegment] = []
        buffer_text: list[str] = []
        buffer_start: float | None = None
        buffer_end: float | None = None
        buffer_lang: str | None = None

        for seg in segments:
            if buffer_start is None:
                buffer_start = seg.start
            buffer_end = seg.end
            buffer_text.extend(seg.text.split())
            buffer_lang = seg.language or buffer_lang
            duration = buffer_end - buffer_start
            if duration >= self.PREFERRED_MIN_DURATION:
                text = join_asr_words(buffer_text)
                merged.append(
                    MergedSegment(
                        start=buffer_start,
                        end=min(buffer_end, buffer_start + self.MAX_DURATION),
                        text=text,
                        speaker="SPEAKER_00",
                        lang=resolve_segment_lang(
                            buffer_text, fallback=self._normalize_lang(buffer_lang)
                        ),
                    )
                )
                buffer_text = []
                buffer_start = None
                buffer_end = None

        if buffer_text and buffer_start is not None and buffer_end is not None:
            merged.append(
                MergedSegment(
                    start=buffer_start,
                    end=buffer_end,
                    text=join_asr_words(buffer_text),
                    speaker="SPEAKER_00",
                    lang=resolve_segment_lang(
                        buffer_text, fallback=self._normalize_lang(buffer_lang)
                    ),
                )
            )
        return merged

    @staticmethod
    def _speaker_at(turns: list[DiarizationTurn], start: float, end: float) -> str:
        best_speaker: str | None = None
        best_overlap = 0.0
        for turn in turns:
            overlap = min(end, turn.end) - max(start, turn.start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = turn.speaker
        if best_speaker:
            return best_speaker
        return turns[0].speaker if turns else "SPEAKER_00"

    @staticmethod
    def _normalize_lang(lang: str | None) -> str:
        if not lang:
            return "mix"
        lang = lang.lower()
        if lang.startswith("en"):
            return "en"
        if lang.startswith("fr"):
            return "fr"
        return "mix"

    @staticmethod
    def cut_segment_wav(source_wav: str, output_wav: str, start: float, end: float) -> None:
        duration = max(0.01, end - start)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                source_wav,
                "-t",
                str(duration),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                output_wav,
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def wav_duration(path: str) -> float:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
