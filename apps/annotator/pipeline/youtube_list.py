"""Parse docs/youtube-sources.md into importable YouTube entries."""

from __future__ import annotations

import re

_HEADING = re.compile(r"^## (.+)$")
_LINK = re.compile(r"^- \[([^\]]+)\]\((https://www\.youtube\.com/watch\?v=[^)]+)\)\s*$")
_BARE = re.compile(r"^- (https://www\.youtube\.com/watch\?v=\S+)\s*$")
_VIDEO_ID = re.compile(r"v=([A-Za-z0-9_-]{11})")


def youtube_video_id(url: str) -> str | None:
    match = _VIDEO_ID.search(url)
    return match.group(1) if match else None


def parse_youtube_sources_md(text: str) -> list[dict[str, str]]:
    collection = ""
    items: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        heading = _HEADING.match(line)
        if heading:
            collection = heading.group(1).strip()
            continue
        link = _LINK.match(line)
        if link:
            title, url = link.group(1), link.group(2)
            video_id = youtube_video_id(url)
            if video_id:
                items.append(
                    {"collection": collection, "title": title, "url": url, "video_id": video_id}
                )
            continue
        bare = _BARE.match(line)
        if bare:
            url = bare.group(1)
            video_id = youtube_video_id(url)
            if video_id:
                items.append(
                    {"collection": collection, "title": "", "url": url, "video_id": video_id}
                )
    return items
