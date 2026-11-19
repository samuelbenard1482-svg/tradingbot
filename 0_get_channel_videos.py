"""
Step 0: Enumerate every video URL on a YouTube channel and write them to
video_urls.txt, ready for 1_extract_transcripts.py to consume.

Usage:
    python 0_get_channel_videos.py https://www.youtube.com/@InnerCircleTrader/videos

Requires: pip install yt-dlp
(yt-dlp is the actively maintained fork of youtube-dl and handles channel
 pages, "/videos" tabs, and uploads playlists reliably.)

Notes:
- This only lists video URLs + titles — it does NOT download video/audio.
- The Inner Circle Trader channel has 875+ videos as of writing, so this
  may take a minute or two to enumerate (yt-dlp paginates through the
  channel's video grid).
- You can re-run this any time to pick up new uploads; it overwrites
  video_urls.txt, so copy it elsewhere first if you've hand-edited it.
"""

import subprocess
import sys
from pathlib import Path

OUTPUT_FILE = Path("video_urls.txt")


def main():
    if len(sys.argv) != 2:
        print("Usage: python 0_get_channel_videos.py <channel_url>")
        print("Example: python 0_get_channel_videos.py https://www.youtube.com/@InnerCircleTrader/videos")
        sys.exit(1)

    channel_url = sys.argv[1]

    print(f"Enumerating videos from {channel_url} ...")
    print("(This lists metadata only — no video/audio is downloaded.)")

    # --flat-playlist avoids resolving each video's full metadata (fast).
    # --print gives us "url<TAB>title" per line via a custom template.
    result = subprocess.run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--print", "%(webpage_url)s\t%(title)s",
            channel_url,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("yt-dlp failed:")
        print(result.stderr)
        sys.exit(1)

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    print(f"Found {len(lines)} videos.")

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        f.write(f"# Auto-generated from {channel_url}\n")
        f.write(f"# {len(lines)} videos found\n")
        for line in lines:
            url, _, title = line.partition("\t")
            f.write(f"{url}  # {title}\n")

    print(f"Wrote {len(lines)} video URLs to {OUTPUT_FILE}")
    print("Next: python 1_extract_transcripts.py")


if __name__ == "__main__":
    main()
