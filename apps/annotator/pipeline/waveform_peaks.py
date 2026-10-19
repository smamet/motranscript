"""Precompute WaveSurfer-compatible peak envelopes from mono WAV files."""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

PEAKS_VERSION = 2
PEAKS_FILENAME = "peaks.json"
# Dense enough that a ~10s zoom window still has hundreds of samples.
BUCKETS_PER_SEC = 80
MAX_POINTS = 250_000
_SAMPLE_MAX = 32768.0  # s16 absolute scale (maps -32768..32767 → ~-1..1)


def peaks_path_for(wav_path: Path) -> Path:
    return wav_path.with_name(PEAKS_FILENAME)


def compute_waveform_peaks(
    wav_path: Path,
    *,
    buckets_per_sec: int = BUCKETS_PER_SEC,
    max_points: int = MAX_POINTS,
) -> dict[str, Any]:
    """Stream a mono (or first-channel) WAV into a peaks payload for WaveSurfer v7."""
    with wave.open(str(wav_path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        if nchannels < 1 or sampwidth != 2 or framerate <= 0 or nframes <= 0:
            raise ValueError(
                f"Unsupported WAV for peaks: channels={nchannels} "
                f"width={sampwidth} rate={framerate} frames={nframes}"
            )

        duration = nframes / float(framerate)
        target_points = max(1, min(max_points, int(math.ceil(duration * buckets_per_sec))))
        frames_per_bucket = max(1, math.ceil(nframes / target_points))

        peaks: list[float] = []
        remaining = nframes
        # Process in chunks of frames_per_bucket
        while remaining > 0:
            take = min(frames_per_bucket, remaining)
            raw = wf.readframes(take)
            remaining -= take
            if not raw:
                break
            # Unpack interleaved s16; take first channel only
            n_samples = len(raw) // 2
            samples = struct.unpack(f"<{n_samples}h", raw)
            if nchannels == 1:
                channel = samples
            else:
                channel = samples[0::nchannels]
            if not channel:
                peaks.append(0.0)
                continue
            peak = max(abs(s) for s in channel) / _SAMPLE_MAX
            peaks.append(round(min(1.0, peak), 4))

    return {
        "version": PEAKS_VERSION,
        "duration": round(duration, 3),
        "peaks": [peaks],
    }


def write_waveform_peaks(wav_path: Path, peaks_path: Path | None = None) -> Path:
    """Compute peaks and write peaks.json next to the WAV. Returns the peaks path."""
    out = peaks_path or peaks_path_for(wav_path)
    payload = compute_waveform_peaks(wav_path)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return out


def _peaks_file_current(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("version") == PEAKS_VERSION


def ensure_waveform_peaks(wav_path: Path) -> Path | None:
    """Return existing peaks.json or generate it. None if wav missing.

    Regenerates when the file is missing or an older peaks version.
    """
    if not wav_path.exists():
        return None
    out = peaks_path_for(wav_path)
    if out.exists() and _peaks_file_current(out):
        return out
    write_waveform_peaks(wav_path, out)
    return out


def load_or_create_peaks(wav_path: Path) -> dict[str, Any]:
    """Load peaks.json or create it; raises if WAV is missing/unreadable."""
    path = ensure_waveform_peaks(wav_path)
    if path is None:
        raise FileNotFoundError(f"Audio missing: {wav_path}")
    return json.loads(path.read_text(encoding="utf-8"))
