# YouTube Best-Quality MP4 Downloader

Download YouTube videos as best-quality MP4 (best video + best audio merged with FFmpeg), using [yt-dlp](https://github.com/yt-dlp/yt-dlp). Supports single videos, playlists, and channels.

## Requirements

- Python 3.10+
- FFmpeg on your PATH (needed to merge video and audio)

### Install FFmpeg (Windows)

```powershell
winget install Gyan.FFmpeg
```

Confirm it works (open a **new** terminal after install):

```powershell
ffmpeg -version
```

### Install Python deps

```powershell
pip install -r requirements.txt
```

Keep yt-dlp updated when YouTube changes break downloads:

```powershell
pip install -U yt-dlp
```

## Usage

### GUI

```powershell
python gui.py
```

Or double-click `run.bat`.

Paste a video, playlist, or channel URL, choose a save folder, click **Download best MP4**.

### CLI

Single video:

```powershell
python download.py "https://www.youtube.com/watch?v=VIDEO_ID" -o ./downloads --no-playlist
```

Playlist or channel (all videos, or cap with `-n`):

```powershell
python download.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" -o ./downloads
python download.py "https://www.youtube.com/@ChannelName/videos" -o ./downloads -n 10
```

### Python API

```python
from download import download_video, download_videos

path = download_video("https://www.youtube.com/watch?v=VIDEO_ID", output_dir="./downloads")

paths = download_videos(
    "https://www.youtube.com/playlist?list=PLAYLIST_ID",
    output_dir="./downloads",
    playlist=True,
    max_downloads=20,  # optional
)
```

### Optional: build a portable EXE

```powershell
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name YoutubeMP4Downloader --collect-all yt_dlp gui.py
```

The exe lands in `dist/`. FFmpeg must still be installed on the PC.

## Notes

- Single videos: `Title [video_id].mp4`
- Playlists/channels: saved under a subfolder named after the list/channel
- GUI checkbox **Download all videos in playlist / channel** controls batch mode; **Max videos** limits large channels
