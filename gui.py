"""Simple tkinter UI for best-quality YouTube MP4 downloads."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from download import FFmpegNotFoundError, download_videos, ensure_ffmpeg
from yt_dlp.utils import DownloadError


class DownloaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("YouTube MP4 Downloader")
        self.minsize(560, 280)
        self.resizable(True, False)

        self._busy = False
        self._current_index = 0
        self._current_total: int | None = None
        self._build_ui()
        self.after(100, self._check_ffmpeg)

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="YouTube URL").grid(row=0, column=0, sticky=tk.W, **pad)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(root, textvariable=self.url_var, width=60)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, **pad)

        ttk.Label(root, text="Save to").grid(row=1, column=0, sticky=tk.W, **pad)
        self.dir_var = tk.StringVar(value=str(Path.cwd() / "downloads"))
        ttk.Entry(root, textvariable=self.dir_var).grid(
            row=1, column=1, sticky=tk.EW, **pad
        )
        ttk.Button(root, text="Browse…", command=self._browse).grid(
            row=1, column=2, sticky=tk.E, **pad
        )

        options = ttk.Frame(root)
        options.grid(row=2, column=0, columnspan=3, sticky=tk.EW, **pad)

        self.playlist_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options,
            text="Download all videos in playlist / channel",
            variable=self.playlist_var,
        ).pack(side=tk.LEFT)

        ttk.Label(options, text="Max videos:").pack(side=tk.LEFT, padx=(16, 4))
        self.max_var = tk.StringVar(value="")
        ttk.Entry(options, textvariable=self.max_var, width=6).pack(side=tk.LEFT)
        ttk.Label(options, text="(blank = all)").pack(side=tk.LEFT, padx=(4, 0))

        self.download_btn = ttk.Button(
            root, text="Download best MP4", command=self._start_download
        )
        self.download_btn.grid(row=3, column=1, sticky=tk.W, **pad)

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.grid(row=4, column=0, columnspan=3, sticky=tk.EW, **pad)

        self.status_var = tk.StringVar(
            value="Ready — paste a video, playlist, or channel URL"
        )
        ttk.Label(root, textvariable=self.status_var).grid(
            row=5, column=0, columnspan=3, sticky=tk.W, **pad
        )

        root.columnconfigure(1, weight=1)
        self.url_entry.focus_set()

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.dir_var.get() or ".")
        if chosen:
            self.dir_var.set(chosen)

    def _check_ffmpeg(self) -> None:
        try:
            ensure_ffmpeg()
        except FFmpegNotFoundError as exc:
            self.status_var.set(str(exc))
            messagebox.showwarning("FFmpeg missing", str(exc))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.download_btn.configure(state=state)
        self.url_entry.configure(state=state)

    def _item_hook(self, index: int, total: int | None, title: str) -> None:
        self._current_index = index
        self._current_total = total
        total_s = str(total) if total else "?"
        short = title if len(title) <= 60 else title[:57] + "..."
        self.after(
            0,
            lambda: self.status_var.set(f"[{index}/{total_s}] {short}"),
        )

    def _progress_hook(self, status: dict[str, Any]) -> None:
        state = status.get("status")
        if state == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            downloaded = status.get("downloaded_bytes") or 0
            if total:
                percent = min(100.0, downloaded * 100.0 / total)
            else:
                raw = (status.get("_percent_str") or "").replace("%", "").strip()
                try:
                    percent = float(raw)
                except ValueError:
                    percent = 0.0
            speed = (status.get("_speed_str") or "").strip() or "?"
            eta = (status.get("_eta_str") or "").strip() or "?"
            idx = self._current_index
            tot = self._current_total
            prefix = f"[{idx}/{tot}] " if idx and tot else (f"[{idx}] " if idx else "")
            self.after(
                0,
                lambda: self._update_progress(
                    percent,
                    f"{prefix}Downloading… {percent:.1f}%  {speed}  ETA {eta}",
                ),
            )
        elif state == "finished":
            self.after(
                0,
                lambda: self._update_progress(100, "Merging with FFmpeg…"),
            )

    def _update_progress(self, percent: float, message: str) -> None:
        self.progress["value"] = percent
        self.status_var.set(message)

    def _parse_max_downloads(self) -> int | None:
        raw = self.max_var.get().strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError("Max videos must be a whole number.") from exc
        if value < 1:
            raise ValueError("Max videos must be at least 1.")
        return value

    def _start_download(self) -> None:
        if self._busy:
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("Missing URL", "Paste a YouTube URL first.")
            return

        try:
            max_downloads = self._parse_max_downloads()
        except ValueError as exc:
            messagebox.showinfo("Invalid max", str(exc))
            return

        output_dir = self.dir_var.get().strip() or "."
        playlist = self.playlist_var.get()
        self._set_busy(True)
        self._current_index = 0
        self._current_total = None
        self.progress["value"] = 0
        self.status_var.set("Starting download…")

        thread = threading.Thread(
            target=self._run_download,
            args=(url, output_dir, playlist, max_downloads),
            daemon=True,
        )
        thread.start()

    def _run_download(
        self,
        url: str,
        output_dir: str,
        playlist: bool,
        max_downloads: int | None,
    ) -> None:
        try:
            paths = download_videos(
                url,
                output_dir=output_dir,
                playlist=playlist,
                max_downloads=max_downloads,
                progress_hook=self._progress_hook,
                item_hook=self._item_hook if playlist else None,
            )
        except Exception as exc:  # noqa: BLE001 — show any failure in the UI
            self.after(0, lambda: self._on_error(exc))
            return
        self.after(0, lambda: self._on_success(paths))

    def _on_success(self, paths: list[Path]) -> None:
        self._set_busy(False)
        self.progress["value"] = 100
        count = len(paths)
        if count == 1:
            self.status_var.set(f"Saved: {paths[0]}")
            messagebox.showinfo("Done", f"Saved:\n{paths[0]}")
            return

        folder = paths[0].parent
        self.status_var.set(f"Saved {count} videos under {folder}")
        preview = "\n".join(p.name for p in paths[:8])
        if count > 8:
            preview += f"\n… and {count - 8} more"
        messagebox.showinfo("Done", f"Saved {count} videos to:\n{folder}\n\n{preview}")

    def _on_error(self, exc: BaseException) -> None:
        self._set_busy(False)
        self.progress["value"] = 0
        message = str(exc) or exc.__class__.__name__
        if isinstance(
            exc, (FFmpegNotFoundError, DownloadError, ValueError, FileNotFoundError)
        ):
            self.status_var.set(message)
        else:
            self.status_var.set(f"Error: {message}")
        messagebox.showerror("Download failed", message)


def main() -> None:
    app = DownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
