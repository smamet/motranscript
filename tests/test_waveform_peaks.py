"""Unit tests for waveform peaks generation."""

import json
import struct
import wave
from pathlib import Path

from apps.annotator.pipeline.waveform_peaks import (
    compute_waveform_peaks,
    ensure_waveform_peaks,
    peaks_path_for,
    write_waveform_peaks,
)


def _write_sine_wav(path: Path, *, duration_sec: float = 1.0, rate: int = 16000, amp: int = 16000) -> None:
    nframes = int(duration_sec * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(nframes):
            # Simple square-ish peak every half second for predictable envelope
            sample = amp if (i // (rate // 4)) % 2 == 0 else -amp
            frames.extend(struct.pack("<h", sample))
        wf.writeframes(frames)


def test_compute_waveform_peaks_duration_and_range(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    _write_sine_wav(wav, duration_sec=2.0)
    payload = compute_waveform_peaks(wav, buckets_per_sec=20, max_points=8000)
    assert payload["version"] == 2
    assert abs(payload["duration"] - 2.0) < 0.01
    peaks = payload["peaks"]
    assert len(peaks) == 1
    assert 20 <= len(peaks[0]) <= 50  # ~40 for 2s @ 20/sec (explicit args)
    assert all(0.0 <= p <= 1.0 for p in peaks[0])
    assert max(peaks[0]) > 0.4


def test_write_and_ensure_waveform_peaks(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    _write_sine_wav(wav, duration_sec=0.5)
    out = write_waveform_peaks(wav)
    assert out == peaks_path_for(wav)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["duration"] > 0
    assert data["peaks"][0]

    # Second call should reuse existing file
    again = ensure_waveform_peaks(wav)
    assert again == out


def test_ensure_regenerates_stale_peaks_version(tmp_path: Path) -> None:
    wav = tmp_path / "audio.wav"
    _write_sine_wav(wav, duration_sec=0.5)
    stale = peaks_path_for(wav)
    stale.write_text(json.dumps({"version": 1, "duration": 0.5, "peaks": [[0.1]]}))
    out = ensure_waveform_peaks(wav)
    assert out == stale
    data = json.loads(stale.read_text())
    assert data["version"] == 2
    assert len(data["peaks"][0]) > 1
