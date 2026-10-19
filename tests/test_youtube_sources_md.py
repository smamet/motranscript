from pathlib import Path

from apps.annotator.pipeline.youtube_list import parse_youtube_sources_md, youtube_video_id


def test_youtube_sources_md_is_clean_and_unique():
    text = Path("docs/youtube-sources.md").read_text(encoding="utf-8")
    items = parse_youtube_sources_md(text)
    assert len(items) == 60
    assert len({item["video_id"] for item in items}) == 60
    assert "pp=" not in text
    assert "&t=" not in text
    collections = {item["collection"] for item in items}
    assert collections == {"Lir Ekril Kreol Morisien", "Komiko", "Tempo La So"}
    assert youtube_video_id("https://www.youtube.com/watch?v=-GCsPtlhqvY") == "-GCsPtlhqvY"
