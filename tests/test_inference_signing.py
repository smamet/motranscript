"""Tests for signed audio URLs used by RunPod."""

from apps.annotator.config import get_settings
from apps.annotator.pipeline.inference import sign_audio_url, verify_audio_signature


def test_audio_signature_roundtrip(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://asr.example.com")
    get_settings.cache_clear()

    url = sign_audio_url(42, ttl_seconds=60)
    assert "/api/internal/audio/42?" in url
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    exp = int(qs["exp"][0])
    sig = qs["sig"][0]
    assert verify_audio_signature(42, exp, sig)
    assert not verify_audio_signature(43, exp, sig)
    assert not verify_audio_signature(42, exp - 10_000, sig)

    get_settings.cache_clear()
