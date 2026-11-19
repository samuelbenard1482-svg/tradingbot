"""
Step 2: Turn raw transcripts into structured ICT rule definitions using Claude.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python 2_extract_rules.py

Reads every transcripts/<video_id>.txt file, sends it to Claude with the
extraction prompt, and writes structured rules to rules/<video_id>.json.
Finally merges everything into rules/combined_rules.json (deduplicated by
concept_name).

Requires: pip install anthropic
"""

import json
import os
import re
from pathlib import Path

import anthropic

TRANSCRIPTS_DIR = Path("transcripts")
RULES_DIR = Path("rules")
PROMPT_FILE = Path("extraction_prompt.md")
COMBINED_FILE = RULES_DIR / "combined_rules.json"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8000

# Transcripts longer than this (characters) get split into chunks so we don't
# blow past context / miss content on very long videos.
CHUNK_SIZE = 60000


def chunk_text(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [text]


def call_claude(client: anthropic.Anthropic, system_prompt: str, transcript_chunk: str) -> list:
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Transcript:\n\n{transcript_chunk}",
            }
        ],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    text = re.sub(r"^```json|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    [warn] Could not parse JSON from model output: {e}")
        return []


def dedupe_rules(rules: list) -> list:
    seen = {}
    for rule in rules:
        key = rule.get("concept_name", "").strip().lower()
        if not key:
            continue
        if key not in seen:
            seen[key] = rule
        else:
            # Keep the richer entry (more populated fields)
            existing_richness = sum(bool(v) for v in seen[key].values())
            new_richness = sum(bool(v) for v in rule.values())
            if new_richness > existing_richness:
                seen[key] = rule
    return list(seen.values())


def main():
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("Set ANTHROPIC_API_KEY in your environment before running this script.")
        return

    if not TRANSCRIPTS_DIR.exists():
        print(f"No {TRANSCRIPTS_DIR} directory found. Run 1_extract_transcripts.py first.")
        return

    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    RULES_DIR.mkdir(exist_ok=True)
    client = anthropic.Anthropic()

    all_rules = []
    transcript_files = sorted(TRANSCRIPTS_DIR.glob("*.txt"))

    if not transcript_files:
        print("No transcripts found to process.")
        return

    for path in transcript_files:
        video_id = path.stem
        print(f"Extracting rules from {video_id} ...")
        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text, CHUNK_SIZE)

        video_rules = []
        for idx, chunk in enumerate(chunks):
            print(f"  chunk {idx + 1}/{len(chunks)} ({len(chunk)} chars)")
            rules = call_claude(client, system_prompt, chunk)
            video_rules.extend(rules)

        video_rules = dedupe_rules(video_rules)
        out_path = RULES_DIR / f"{video_id}.json"
        out_path.write_text(json.dumps(video_rules, indent=2), encoding="utf-8")
        print(f"  -> {len(video_rules)} rules -> {out_path}")

        all_rules.extend(video_rules)

    combined = dedupe_rules(all_rules)
    COMBINED_FILE.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(f"\nDone. {len(combined)} unique concepts merged into {COMBINED_FILE}")


if __name__ == "__main__":
    main()
