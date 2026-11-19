# ICT Wing — Knowledge Extraction Pipeline

Turns a list of YouTube trading-education videos into a structured, de-duplicated
JSON rule base you can feed into your expert system's inference engine.

## Pipeline

```
0_get_channel_videos.py    → video_urls.txt (all videos on a channel)
      │
      ▼
1_extract_transcripts.py   → transcripts/<video_id>.txt + transcripts/manifest.json
      │
      ▼
2_extract_rules.py         → rules/<video_id>.json + rules/combined_rules.json
```

## Setup

```bash
python -m venv venv
source venv/bin/activate        # or venv\Scripts\activate on Windows
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # get one at console.anthropic.com
```

## Usage

**Option A — pull every video from a whole channel:**
```bash
python 0_get_channel_videos.py https://www.youtube.com/@InnerCircleTrader/videos
python 1_extract_transcripts.py
python 2_extract_rules.py
```

**Option B — hand-pick specific videos:**
1. Add video URLs (or bare video IDs) to `video_urls.txt` yourself, one per line.
2. Run:
   ```bash
   python 1_extract_transcripts.py
   python 2_extract_rules.py
   ```

Either way, `rules/combined_rules.json` ends up as your structured knowledge base.

### A note on scale
Channels like The Inner Circle Trader have 800+ uploads. That means:
- Step 0 can take a couple of minutes to enumerate.
- Step 1 will hit videos with no captions/transcripts (older uploads, clips,
  livestream VODs) — these get logged as "failed" in `transcripts/manifest.json`
  and skipped, not silently dropped.
- Step 2 makes one Claude API call per transcript chunk, so running the full
  catalog will use a meaningful number of tokens/API calls. Consider testing
  on a subset first — e.g. trim `video_urls.txt` down to 10-20 videos covering
  the core concept lectures before running the full channel.

## Output format

Each rule looks like:

```json
{
  "concept_name": "Bullish Order Block",
  "category": "order_block",
  "definition": "...",
  "trigger_conditions": ["..."],
  "preconditions": ["..."],
  "directional_bias": "bullish",
  "confidence_notes": "...",
  "conflicts_or_invalidations": ["..."],
  "source_quote_paraphrase": "..."
}
```

This maps directly onto the rule-engine design from the ICT Wing plan:
`category` + `directional_bias` let you group rules by detector type,
`trigger_conditions`/`preconditions` become the actual if-then logic,
and `confidence_notes` feeds your weighting/confidence layer.

## Notes & limitations

- Videos with disabled captions or no transcript will be skipped and logged
  in `transcripts/manifest.json` — you'll need to source those manually
  (e.g., transcribe audio yourself, or find a written breakdown).
- Long transcripts are automatically chunked before being sent to Claude so
  nothing gets truncated or missed; chunks from the same video are merged
  and de-duplicated afterward.
- The extraction prompt (`extraction_prompt.md`) is the main lever for
  quality — tune it if you want different fields, stricter categories, or
  to bias toward specific concepts you care about.
- Review the output before trusting it for trading logic. LLM extraction can
  still misclassify or miss nuance, especially with informal spoken content
  (filler words, tangents, multiple speakers).
- This script never trades or executes anything — it's purely for building
  your knowledge base offline.
