import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from apps.annotator.config import get_settings
from apps.annotator.pipeline.waveform_peaks import write_waveform_peaks
from apps.annotator.pipeline.yt_dlp_args import run_ytdlp


@dataclass
class IngestResult:
    audio_path: Path
    duration_sec: float


class AudioIngestor:
    """Download or normalize audio to 16 kHz mono WAV."""

    TARGET_RATE = 16000

    def ingest_youtube(
        self,
        url: str,
        source_id: int,
        on_phase: Callable[[float, str], None] | None = None,
    ) -> IngestResult:
        settings = get_settings()
        out_dir = settings.sources_dir / str(source_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_path = out_dir / "download"
        wav_path = out_dir / "audio.wav"

        if on_phase:
            on_phase(0.1, "Downloading from YouTube…")

        run_ytdlp(
            [
                "-x",
                "--audio-format",
                "wav",
                "--audio-quality",
                "0",
                "-o",
                str(raw_path),
                url,
            ],
            context="YouTube download failed",
        )
        if on_phase:
            on_phase(0.55, "Download complete — converting…")

        downloaded = next(out_dir.glob("download.*"))
        self._to_wav(downloaded, wav_path)
        if downloaded != wav_path and downloaded.exists():
            downloaded.unlink(missing_ok=True)
        duration = self._probe_duration(wav_path)
        write_waveform_peaks(wav_path)
        return IngestResult(audio_path=wav_path, duration_sec=duration)

    def normalize_upload(self, input_path: Path, source_id: int) -> IngestResult:
        settings = get_settings()
        out_dir = settings.sources_dir / str(source_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        wav_path = out_dir / "audio.wav"
        self._to_wav(input_path, wav_path)
        duration = self._probe_duration(wav_path)
        write_waveform_peaks(wav_path)
        return IngestResult(audio_path=wav_path, duration_sec=duration)

    def _to_wav(self, input_path: Path, output_path: Path) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-ac",
                "1",
                "-ar",
                str(self.TARGET_RATE),
                "-sample_fmt",
                "s16",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _probe_duration(path: Path) -> float:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
