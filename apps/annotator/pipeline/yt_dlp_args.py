"""yt-dlp invocation helpers (Node runtime + readable errors)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_COMMON_NODE_PATHS = (
    "/opt/homebrew/bin/node",
    "/usr/local/bin/node",
)


def resolve_node_executable() -> str | None:
    """Find Node for yt-dlp JS challenges even when worker PATH is minimal."""
    env_path = os.environ.get("YT_DLP_NODE_PATH", "").strip()
    if env_path:
        path = Path(env_path)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    which_node = shutil.which("node")
    if which_node:
        return which_node

    for candidate in _COMMON_NODE_PATHS:
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def resolve_cookies_file() -> str | None:
    """Netscape cookies.txt for YouTube bot checks (needed on datacenter IPs)."""
    env_path = os.environ.get("YT_DLP_COOKIES", "").strip()
    if not env_path:
        return None
    path = Path(env_path)
    if path.is_file() and os.access(path, os.R_OK):
        return str(path)
    return None


def yt_dlp_base_args() -> list[str]:
    """Args required for current YouTube anti-bot / JS challenge handling."""
    args = [sys.executable, "-m", "yt_dlp"]
    node = resolve_node_executable()
    if node:
        args.extend(["--js-runtimes", f"node:{node}"])
    cookies = resolve_cookies_file()
    if cookies:
        args.extend(["--cookies", cookies])
    args.extend(["--remote-components", "ejs:github"])
    return args


def format_ytdlp_error(exc: subprocess.CalledProcessError, *, context: str | None = None) -> str:
    """Extract the useful yt-dlp message instead of the raw subprocess line."""
    combined = "\n".join(part for part in (exc.stderr, exc.stdout) if part)
    lines = [line.strip() for line in combined.splitlines() if line.strip()]

    error_line = next((line for line in reversed(lines) if line.startswith("ERROR:")), None)
    js_warning = next(
        (
            line
            for line in lines
            if "javascript runtime" in line.lower() or "js-runtimes" in line.lower()
        ),
        None,
    )

    if error_line:
        message = error_line.removeprefix("ERROR:").strip()
        if message.startswith("[youtube]") and ": " in message:
            message = message.split(": ", 1)[1]
    elif lines:
        message = lines[-1]
    else:
        message = str(exc)

    if js_warning:
        hint = "Install Node.js or set YT_DLP_NODE_PATH so yt-dlp can solve YouTube JS challenges."
        if hint not in message:
            message = f"{message} ({hint})"

    bot_check = "not a bot" in message.lower() or "cookies-from-browser" in message.lower()
    if bot_check and resolve_cookies_file() is None:
        hint = "Export YouTube cookies and set YT_DLP_COOKIES to the cookies.txt path on the VPS."
        if hint not in message:
            message = f"{message} ({hint})"

    if context:
        return f"{context}: {message}"
    return message


def run_ytdlp(args: list[str], *, context: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run yt-dlp and raise RuntimeError with a readable message on failure."""
    cmd = [*yt_dlp_base_args(), *args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(format_ytdlp_error(exc, context=context)) from exc
