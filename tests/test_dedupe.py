from pathlib import Path

from apps.annotator.api.dedupe import (
    DuplicateSourceError,
    extract_youtube_video_id,
    file_sha256,
    upload_dedupe_key,
    youtube_dedupe_key,
)
from apps.annotator.db.models import Source, SourceType


def test_extracts_youtube_ids_across_url_shapes():
    video_id = "dQw4w9WgXcQ"
    urls = [
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://www.youtube.com/watch?v={video_id}&t=12s",
        f"https://youtu.be/{video_id}",
        f"https://m.youtube.com/watch?v={video_id}",
        f"youtube.com/watch?v={video_id}",
        f"https://www.youtube.com/embed/{video_id}",
        f"https://www.youtube.com/shorts/{video_id}",
        f"https://www.youtube.com/live/{video_id}",
    ]
    assert {extract_youtube_video_id(url) for url in urls} == {video_id}
    assert {youtube_dedupe_key(url) for url in urls} == {f"yt:{video_id}"}


def test_rejects_non_video_urls():
    assert extract_youtube_video_id("https://www.youtube.com/playlist?list=PLxxxx") is None
    assert extract_youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None


def test_upload_hash_is_content_based(tmp_path: Path):
    a = tmp_path / "a.wav"
    b = tmp_path / "renamed.wav"
    c = tmp_path / "other.wav"
    a.write_bytes(b"same-bytes")
    b.write_bytes(b"same-bytes")
    c.write_bytes(b"different")
    assert file_sha256(a) == file_sha256(b)
    assert upload_dedupe_key(a) == upload_dedupe_key(b)
    assert upload_dedupe_key(a) != upload_dedupe_key(c)


def test_duplicate_message_includes_existing_source():
    source = Source(
        source_type=SourceType.youtube,
        title="Evening news",
        source_url="https://youtu.be/dQw4w9WgXcQ",
    )
    source.id = 12
    err = DuplicateSourceError(source)
    assert "#12" in str(err)
    assert "Evening news" in str(err)
