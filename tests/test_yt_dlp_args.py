import subprocess

from apps.annotator.pipeline.yt_dlp_args import (
    format_ytdlp_error,
    resolve_node_executable,
    run_ytdlp,
    yt_dlp_base_args,
)


def test_resolve_node_falls_back_to_homebrew(monkeypatch):
    monkeypatch.delenv("YT_DLP_NODE_PATH", raising=False)
    monkeypatch.setattr("apps.annotator.pipeline.yt_dlp_args.shutil.which", lambda _: None)
    node = resolve_node_executable()
    if __import__("pathlib").Path("/opt/homebrew/bin/node").is_file():
        assert node == "/opt/homebrew/bin/node"


def test_yt_dlp_base_args_includes_cookies(tmp_path, monkeypatch):
    cookies = tmp_path / "youtube.cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("YT_DLP_COOKIES", str(cookies))
    args = yt_dlp_base_args()
    assert "--cookies" in args
    assert args[args.index("--cookies") + 1] == str(cookies)


def test_yt_dlp_base_args_skips_missing_cookies(monkeypatch):
    monkeypatch.setenv("YT_DLP_COOKIES", "/no/such/cookies.txt")
    args = yt_dlp_base_args()
    assert "--cookies" not in args


def test_yt_dlp_base_args_includes_node_path(tmp_path, monkeypatch):
    node = tmp_path / "node"
    node.write_text("#!/bin/sh\n")
    node.chmod(0o755)
    monkeypatch.setenv("YT_DLP_NODE_PATH", str(node))
    monkeypatch.setattr("apps.annotator.pipeline.yt_dlp_args.shutil.which", lambda _: None)
    args = yt_dlp_base_args()
    assert "--js-runtimes" in args
    idx = args.index("--js-runtimes")
    assert args[idx + 1] == f"node:{node}"


def test_format_ytdlp_error_extracts_message():
    exc = subprocess.CalledProcessError(
        1,
        "yt-dlp",
        stderr=(
            "WARNING: [youtube] No supported JavaScript runtime could be found.\n"
            "ERROR: [youtube] abc123: This video is not available\n"
        ),
    )
    msg = format_ytdlp_error(exc, context="YouTube download failed")
    assert "YouTube download failed" in msg
    assert "This video is not available" in msg
    assert "YT_DLP_NODE_PATH" in msg


def test_format_ytdlp_error_hints_cookies_on_bot_check(monkeypatch):
    monkeypatch.delenv("YT_DLP_COOKIES", raising=False)
    exc = subprocess.CalledProcessError(
        1,
        "yt-dlp",
        stderr="ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser\n",
    )
    msg = format_ytdlp_error(exc, context="YouTube download failed")
    assert "YT_DLP_COOKIES" in msg
    assert "not a bot" in msg


def test_run_ytdlp_raises_runtime_error(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "yt-dlp", stderr="ERROR: [youtube] x: unavailable")

    monkeypatch.setattr("apps.annotator.pipeline.yt_dlp_args.subprocess.run", fake_run)
    try:
        run_ytdlp(["--no-download", "https://example.com"], context="Probe failed")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Probe failed" in str(exc)
        assert "unavailable" in str(exc)
