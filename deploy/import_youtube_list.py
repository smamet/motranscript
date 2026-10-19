#!/usr/bin/env python3
"""Import docs/youtube-sources.md: create sources and queue ingest only (ASR stays pending)."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from apps.annotator.api.services import create_source_from_youtube
from apps.annotator.api.source_management import resume_source
from apps.annotator.api.categories import resolve_category_id
from apps.annotator.db.models import Source, SourceStatus
from apps.annotator.db.session import SessionLocal
from apps.annotator.pipeline.youtube_list import parse_youtube_sources_md, youtube_video_id


def _existing_by_video_id(db: Session) -> dict[str, Source]:
    found: dict[str, Source] = {}
    for source in db.query(Source).filter(Source.source_url.isnot(None)).all():
        video_id = youtube_video_id(source.source_url or "")
        if video_id and video_id not in found:
            found[video_id] = source
    return found


def import_list(db: Session, items: list[dict[str, str]]) -> dict[str, int]:
    existing = _existing_by_video_id(db)
    stats = {"created": 0, "resumed": 0, "skipped": 0}
    for item in items:
        source = existing.get(item["video_id"])
        if source:
            if source.audio_path:
                stats["skipped"] += 1
                continue
            if source.status == SourceStatus.processing:
                stats["skipped"] += 1
                continue
            try:
                resume_source(db, source.id)
                stats["resumed"] += 1
            except ValueError:
                stats["skipped"] += 1
            continue
        cat_id = resolve_category_id(db, collection=item.get("collection") or None)
        created = create_source_from_youtube(
            db,
            youtube_url=item["url"],
            title=item["title"] or None,
            license_notes=item["collection"] or None,
            category_id=cat_id,
        )
        existing[item["video_id"]] = created
        stats["created"] += 1
    return stats


def main() -> int:
    md_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/app/docs/youtube-sources.md")
    if not md_path.is_file():
        md_path = Path("docs/youtube-sources.md")
    items = parse_youtube_sources_md(md_path.read_text(encoding="utf-8"))
    if not items:
        print("No videos found in", md_path)
        return 1
    db = SessionLocal()
    try:
        stats = import_list(db, items)
    finally:
        db.close()
    print(f"videos={len(items)} created={stats['created']} resumed={stats['resumed']} skipped={stats['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
