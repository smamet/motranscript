from dataclasses import dataclass

from apps.annotator.pipeline.yt_dlp_args import run_ytdlp


@dataclass
class YouTubeMetadata:
    title: str | None
    duration_sec: float | None
    error: str | None = None


def fetch_youtube_metadata(url: str) -> YouTubeMetadata:
    """Best-effort title/duration via yt-dlp without downloading."""
    try:
        result = run_ytdlp(
            [
                "--no-download",
                "--print",
                "%(title)s",
                "--print",
                "%(duration)s",
                url,
            ],
        )
    except RuntimeError as exc:
        return YouTubeMetadata(title=None, duration_sec=None, error=str(exc))

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return YouTubeMetadata(title=lines[0] if lines else None, duration_sec=None)

    title = lines[0]
    try:
        duration = float(lines[1])
    except ValueError:
        duration = None
    return YouTubeMetadata(title=title, duration_sec=duration)
