"""
Live XAUUSD chart with the detector engine actually running on incoming
candles — not just plotting price. Builds on xauusd_live_candles.py's
tick-to-candle aggregation, then runs fair value gap and order block
detection on the closed-candle history after each new candle completes,
annotating any newly-found signals directly on the chart.

Usage:
    pip install requests matplotlib pandas
    export TWELVE_DATA_API_KEY=your_key_here
    python xauusd_live_detectors.py

Detection cadence: detectors only need to re-run when a candle CLOSES
(not on every tick), since FVGs/order blocks are defined over closed
candles. Ticks still update the live-forming candle on the chart, but
the detector stack only re-evaluates on candle close — this keeps CPU
usage low and avoids the flicker of re-detecting "signals" on a candle
that's still changing shape.
"""

from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from collections import deque

import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from engine.aggregation import TickAggregator, Candle
from engine.fair_value_gaps import detect_fair_value_gaps, mark_fill_status, FairValueGap
from engine.order_blocks import detect_displacement, detect_order_blocks, OrderBlock

API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
SYMBOL = "XAU/USD"
POLL_SECONDS = 15
CANDLE_SECONDS = 60
MAX_CANDLES = 120  # keep more history than the plain chart, since detectors need runway
BASE_URL = "https://api.twelvedata.com/price"

# Detector tuning — these are starting-point guesses (see backtest_thresholds.py
# to calibrate properly once you have historical gold data). Gold's tick size
# and typical volatility differ from NASDAQ futures, so don't assume the
# transcript-derived NASDAQ figures transfer directly.
DISPLACEMENT_LOOKBACK = 15
DISPLACEMENT_MIN_MULTIPLE = 2.0


def fetch_price() -> tuple[datetime, float] | None:
    try:
        resp = requests.get(BASE_URL, params={"symbol": SYMBOL, "apikey": API_KEY}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "price" not in data:
            print(f"Unexpected response: {data}")
            return None
        return datetime.now(timezone.utc), float(data["price"])
    except requests.RequestException as e:
        print(f"Fetch error (will retry): {e}")
        return None


def candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    idx = [c.bucket_start for c in candles]
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
        },
        index=pd.DatetimeIndex(idx),
    )


def run_detectors(df: pd.DataFrame) -> tuple[list[FairValueGap], list[OrderBlock]]:
    """Re-runs the FVG and order-block detectors over the full candle history so far."""
    gaps = detect_fair_value_gaps(df)
    gaps = mark_fill_status(df, gaps)
    legs = detect_displacement(df, lookback=DISPLACEMENT_LOOKBACK, min_multiple=DISPLACEMENT_MIN_MULTIPLE)
    blocks = detect_order_blocks(df, legs)
    return gaps, blocks


def draw_chart(ax, candles: list[Candle], current: Candle | None, gaps: list[FairValueGap], blocks: list[OrderBlock]):
    ax.clear()
    all_candles = candles + ([current] if current else [])
    if not all_candles:
        return

    for i, c in enumerate(all_candles):
        is_current = current is not None and i == len(all_candles) - 1
        color = "#c9a227" if c.close >= c.open else "#8b3a3a"
        alpha = 0.5 if is_current else 1.0
        ax.plot([i, i], [c.low, c.high], color=color, linewidth=1, alpha=alpha)
        body_bottom = min(c.open, c.close)
        body_height = abs(c.close - c.open) or 0.01
        ax.add_patch(plt.Rectangle((i - 0.3, body_bottom), 0.6, body_height, color=color, alpha=alpha))

    # Overlay unfilled fair value gaps as shaded rectangles
    for g in gaps:
        if g.filled:
            continue
        color = "#4a7fb5" if g.kind == "bullish" else "#b56b4a"
        ax.axhspan(g.gap_low, g.gap_high, xmin=(g.candle3_idx) / max(len(all_candles), 1),
                   xmax=1.0, color=color, alpha=0.15)

    # Mark order blocks with a horizontal line at their open price
    for b in blocks:
        marker_color = "#2e7d32" if b.kind == "bullish" else "#c62828"
        ax.axhline(b.open_price, color=marker_color, linestyle="--", linewidth=0.8, alpha=0.6)

    ax.set_xlim(-1, len(all_candles))
    labels = [c.bucket_start.strftime("%H:%M") for c in all_candles]
    step = max(1, len(labels) // 12)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)], rotation=45, ha="right")

    last = all_candles[-1]
    unfilled_gaps = sum(1 for g in gaps if not g.filled)
    ax.set_title(
        f"XAU/USD live — {CANDLE_SECONDS}s candles   last: {last.close:.2f}   "
        f"unfilled FVGs: {unfilled_gaps}   order blocks: {len(blocks)}"
    )
    ax.set_ylabel("Price (USD)")


def main():
    if not API_KEY:
        print("Set TWELVE_DATA_API_KEY first. Free key: https://twelvedata.com/pricing")
        sys.exit(1)

    aggregator = TickAggregator(interval_seconds=CANDLE_SECONDS)
    closed_candles: deque[Candle] = deque(maxlen=MAX_CANDLES)
    gaps: list[FairValueGap] = []
    blocks: list[OrderBlock] = []
    seen_gap_ids: set[tuple] = set()

    fig, ax = plt.subplots(figsize=(13, 6.5))

    def update(_frame):
        nonlocal gaps, blocks

        result = fetch_price()
        if result is None:
            return
        ts, price = result
        closed = aggregator.add_tick(ts, price)

        if closed is not None:
            closed_candles.append(closed)
            # Only re-run detectors when we actually have a new closed candle
            if len(closed_candles) >= 5:
                df = candles_to_df(list(closed_candles))
                gaps, blocks = run_detectors(df)

                # Print (once) any FVG we haven't already announced
                for g in gaps:
                    gap_id = (g.kind, round(g.gap_low, 2), round(g.gap_high, 2))
                    if gap_id not in seen_gap_ids:
                        seen_gap_ids.add(gap_id)
                        print(f"[{closed.bucket_start.strftime('%H:%M:%S')}] "
                              f"New {g.kind} FVG: {g.gap_low:.2f}-{g.gap_high:.2f} "
                              f"(midpoint {g.midpoint:.2f})")

        draw_chart(ax, list(closed_candles), aggregator.peek_current(), gaps, blocks)

    ani = animation.FuncAnimation(fig, update, interval=POLL_SECONDS * 1000, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
