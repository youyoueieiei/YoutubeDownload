"""Download YouTube videos as best-quality MP4 via yt-dlp + FFmpeg."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

ProgressHook = Callable[[dict[str, Any]], None]
ItemHook = Callable[[int, int | None, str], None]


class FFmpegNotFoundError(RuntimeError):
    """Raised when FFmpeg is required but not available on PATH."""


def ensure_ffmpeg() -> str:
    """Return the FFmpeg executable path, or raise if missing."""
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegNotFoundError(
            "FFmpeg was not found on PATH. Install it (e.g. "
            "`winget install Gyan.FFmpeg`), open a new terminal, "
            "and confirm with `ffmpeg -version`."
        )
    return path


def _console_progress_hook(status: dict[str, Any]) -> None:
    if status.get("status") == "downloading":
        percent = status.get("_percent_str", "").strip() or "?"
        speed = status.get("_speed_str", "").strip() or "?"
        eta = status.get("_eta_str", "").strip() or "?"
        print(f"\rDownloading: {percent}  speed={speed}  ETA={eta}   ", end="", flush=True)
    elif status.get("status") == "finished":
        print("\nDownload finished, merging with FFmpeg if needed...")


def _resolve_mp4_path(ydl: YoutubeDL, info: dict[str, Any], out_dir: Path) -> Path | None:
    """Resolve the on-disk MP4 path for a downloaded entry."""
    final_path = Path(ydl.prepare_filename(info))
    if final_path.suffix.lower() != ".mp4":
        final_path = final_path.with_suffix(".mp4")

    if final_path.is_file():
        return final_path.resolve()

    video_id = info.get("id")
    if video_id:
        candidates = sorted(
            out_dir.rglob(f"*{video_id}*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0].resolve()
    return None


def _paths_from_info(ydl: YoutubeDL, info: dict[str, Any], out_dir: Path) -> list[Path]:
    paths: list[Path] = []
    if "entries" in info:
        for entry in info["entries"]:
            if not entry:
                continue
            if "entries" in entry:
                paths.extend(_paths_from_info(ydl, entry, out_dir))
                continue
            path = _resolve_mp4_path(ydl, entry, out_dir)
            if path is not None:
                paths.append(path)
    else:
        path = _resolve_mp4_path(ydl, info, out_dir)
        if path is not None:
            paths.append(path)
    return paths


def download_videos(
    url: str,
    output_dir: str | Path = ".",
    filename: str | None = None,
    *,
    playlist: bool = True,
    max_downloads: int | None = None,
    progress_hook: ProgressHook | None = None,
    item_hook: ItemHook | None = None,
) -> list[Path]:
    """
    Download one video, or every video in a playlist/channel, as best-quality MP4.

    Args:
        url: YouTube video, playlist, or channel URL.
        output_dir: Directory to write files into.
        filename: Optional base name (single video only; ignored for playlists).
        playlist: If True, download all items when the URL is a playlist/channel.
            If False, download only the single video (Youtube DLG–style).
        max_downloads: Optional cap on how many videos to fetch (useful for channels).
        progress_hook: Optional yt-dlp progress callback.
        item_hook: Optional callback ``(index, total_or_None, title)`` when each
            item starts downloading.

    Returns:
        List of saved ``.mp4`` paths (may be empty if nothing succeeded).
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("url must be a non-empty YouTube URL")

    ensure_ffmpeg()

    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if filename and not playlist:
        base = Path(filename).stem
        outtmpl = str(out_dir / f"{base}.%(ext)s")
    elif playlist:
        # Playlist/channel: subfolder per list, numbered files
        outtmpl = str(
            out_dir
            / "%(playlist_title|uploader|Channel)s"
            / "%(playlist_index&{} - |)s%(title)s [%(id)s].%(ext)s"
        )
    else:
        outtmpl = str(out_dir / "%(title)s [%(id)s].%(ext)s")

    hook = progress_hook if progress_hook is not None else _console_progress_hook
    seen_ids: set[str] = set()

    def _combined_hook(status: dict[str, Any]) -> None:
        if item_hook and status.get("status") == "downloading":
            info = status.get("info_dict") or {}
            video_id = info.get("id")
            if video_id and video_id not in seen_ids:
                seen_ids.add(video_id)
                index = info.get("playlist_index") or len(seen_ids)
                total = (
                    info.get("n_entries")
                    or info.get("playlist_count")
                    or (max_downloads if max_downloads else None)
                )
                title = info.get("title") or video_id or "video"
                item_hook(int(index), int(total) if total else None, str(title))
        hook(status)

    opts: dict[str, Any] = {
        "format": (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": outtmpl,
        "noplaylist": not playlist,
        "ignoreerrors": playlist,  # keep going if one video in a list fails
        "progress_hooks": [_combined_hook],
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
    }
    if max_downloads is not None and max_downloads > 0:
        opts["playlistend"] = max_downloads

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError("No video information returned")

            paths = _paths_from_info(ydl, info, out_dir)
            if not paths:
                raise FileNotFoundError(
                    f"Download finished but no MP4 files were found under {out_dir}"
                )
            return paths
    except DownloadError as exc:
        message = str(exc)
        if "ffmpeg" in message.lower():
            raise FFmpegNotFoundError(
                "yt-dlp needs FFmpeg to merge video and audio. "
                "Install FFmpeg and ensure it is on PATH."
            ) from exc
        raise


def download_video(
    url: str,
    output_dir: str | Path = ".",
    filename: str | None = None,
    progress_hook: ProgressHook | None = None,
) -> Path:
    """
    Download a single YouTube URL as best-quality MP4 (ignores playlist/channel).

    Returns:
        Path to the resulting .mp4 file.
    """
    paths = download_videos(
        url,
        output_dir=output_dir,
        filename=filename,
        playlist=False,
        progress_hook=progress_hook,
    )
    return paths[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download YouTube video(s) as best-quality MP4 "
        "(video+audio merged with FFmpeg). Supports playlists and channels.",
    )
    parser.add_argument("url", help="YouTube video, playlist, or channel URL")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Directory to save MP4 files (default: current directory)",
    )
    parser.add_argument(
        "-f",
        "--filename",
        default=None,
        help="Optional output base name without extension (single video only)",
    )
    parser.add_argument(
        "--playlist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download all videos in a playlist/channel (default: yes). "
        "Use --no-playlist for a single video only.",
    )
    parser.add_argument(
        "-n",
        "--max-downloads",
        type=int,
        default=None,
        help="Max number of videos to download from a playlist/channel",
    )
    args = parser.parse_args(argv)

    def item_hook(index: int, total: int | None, title: str) -> None:
        total_s = str(total) if total else "?"
        print(f"\n[{index}/{total_s}] {title}")

    try:
        paths = download_videos(
            args.url,
            args.output_dir,
            args.filename,
            playlist=args.playlist,
            max_downloads=args.max_downloads,
            item_hook=item_hook if args.playlist else None,
        )
    except (ValueError, FFmpegNotFoundError, DownloadError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"\nSaved {len(paths)} file(s):")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
