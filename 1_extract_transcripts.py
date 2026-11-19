"""
Step 1: Pull raw transcripts for a list of YouTube videos.

Usage:
    python 1_extract_transcripts.py

Reads video URLs/IDs from video_urls.txt (one per line).
Writes one .txt file per video into transcripts/<video_id>.txt
Also writes a manifest.json mapping video_id -> {url, title(if available), status}

Requires: pip install youtube-transcript-api
"""

import json
import re
import sys
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

INPUT_FILE = Path("video_urls.txt")
OUTPUT_DIR = Path("transcripts")
MANIFEST_FILE = OUTPUT_DIR / "manifest.json"

# Preferred transcript languages, in order of preference.
LANGUAGE_PREFERENCES = ["en", "en-US", "en-GB"]


def extract_video_id(url_or_id: str) -> str:
    """Accepts a full YouTube URL or a bare video ID and returns the video ID."""
    url_or_id = url_or_id.strip()
    if not url_or_id or url_or_id.startswith("#"):
        return ""

    patterns = [
        r"(?:v=|/)([0-9A-Za-z_-]{11}).*",  # watch?v=ID or /ID
        r"youtu\.be/([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    # Assume it's already a bare video ID (11 chars, typical YouTube ID format)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url_or_id):
        return url_or_id

    return ""


def fetch_transcript(video_id: str) -> str | None:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_transcript(LANGUAGE_PREFERENCES)
        except NoTranscriptFound:
            # Fall back to auto-generated or any available transcript, then translate to English
            transcript = transcript_list.find_generated_transcript(
                [t.language_code for t in transcript_list]
            )
            if transcript.language_code not in LANGUAGE_PREFERENCES:
                transcript = transcript.translate("en")

        entries = transcript.fetch()
        full_text = " ".join(entry["text"].strip() for entry in entries if entry["text"].strip())
        return full_text

    except TranscriptsDisabled:
        print(f"  [skip] Transcripts disabled for {video_id}")
    except NoTranscriptFound:
        print(f"  [skip] No transcript found for {video_id}")
    except VideoUnavailable:
        print(f"  [skip] Video unavailable: {video_id}")
    except Exception as e:
        print(f"  [error] {video_id}: {e}")
    return None


def main():
    if not INPUT_FILE.exists():
        print(f"Missing {INPUT_FILE}. Create it with one video URL/ID per line.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    lines = INPUT_FILE.read_text(encoding="utf-8").splitlines()
    manifest = {}

    for raw_line in lines:
        video_id = extract_video_id(raw_line)
        if not video_id:
            continue

        print(f"Fetching transcript for {video_id} ...")
        text = fetch_transcript(video_id)

        out_path = OUTPUT_DIR / f"{video_id}.txt"
        if text:
            out_path.write_text(text, encoding="utf-8")
            manifest[video_id] = {"source": raw_line.strip(), "status": "ok", "chars": len(text)}
            print(f"  [ok] {len(text)} chars -> {out_path}")
        else:
            manifest[video_id] = {"source": raw_line.strip(), "status": "failed"}

    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone. Manifest written to {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
