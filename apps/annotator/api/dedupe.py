"""Fingerprint YouTube URLs and uploaded files so the same source is imported once."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from apps.annotator.db.models import Source

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
}


class DuplicateSourceError(Exception):
    def __init__(self, existing: Source):
        self.existing = existing
        label = (
            existing.title
            or existing.original_filename
            or existing.source_url
            or f"#{existing.id}"
        )
        super().__init__(
            f'Already imported as "{label}" (#{existing.id}). Delete it first to re-import.'
        )


def extract_youtube_video_id(url: str) -> str | None:
    raw = url.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]
        return candidate if _YT_ID.match(candidate) else None
    if host in _YT_HOSTS:
        video = parse_qs(parsed.query).get("v", [""])[0]
        if _YT_ID.match(video):
            return video
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
            return parts[1] if _YT_ID.match(parts[1]) else None
    return None


def youtube_dedupe_key(url: str) -> str:
    video_id = extract_youtube_video_id(url)
    if video_id:
        return f"yt:{video_id}"
    normalized = url.strip()
    if "://" not in normalized:
        normalized = f"https://{normalized}"
    return f"yturl:{normalized.lower()}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_dedupe_key(path: Path) -> str:
    return f"sha256:{file_sha256(path)}"


def find_duplicate(db: Session, key: str) -> Source | None:
    return db.query(Source).filter(Source.dedupe_key == key).first()


def require_new_key(db: Session, key: str) -> None:
    existing = find_duplicate(db, key)
    if existing:
        raise DuplicateSourceError(existing)
