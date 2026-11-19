"""
Live XAUUSD candlestick chart — polls Twelve Data for ticks, aggregates
them into 1-minute candles via TickAggregator, and draws real OHLC bars
(not just a price line).

Usage:
    pip install requests matplotlib
    export TWELVE_DATA_API_KEY=your_key_here   (Windows: set instead of export)
    python xauusd_live_candles.py

Notes on candle quality:
  - With the free-tier poll interval (15s), a 1-minute candle gets ~4
    ticks. That's enough to see real open/high/low/close movement, but
    it's coarser than a true tick feed — the high/low may understate
    the actual intra-minute range, since price could spike between polls
    without being captured. Treat this as a reasonable approximation,
    not exchange-grade data.
  - If you need tighter candles, either shorten CANDLE_SECONDS (fewer
    ticks per candle, so less of an issue) or move to a real streaming
    source (OANDA's practice-account tick stream) later.
"""

from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from collections import deque

import requests
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from engine.aggregation import TickAggregator, Candle

API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
SYMBOL = "XAU/USD"
POLL_SECONDS = 15
CANDLE_SECONDS = 60       # 1-minute candles
MAX_CANDLES = 60          # keep the last hour on screen
BASE_URL = "https://api.twelvedata.com/price"


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


def draw_candles(ax, candles: list[Candle], current: Candle | None):
    ax.clear()
    all_candles = candles + ([current] if current else [])
    if not all_candles:
        return

    for i, c in enumerate(all_candles):
        is_current = current is not None and i == len(all_candles) - 1
        color = "#c9a227" if c.close >= c.open else "#8b3a3a"
        alpha = 0.5 if is_current else 1.0  # dim the still-forming candle

        # wick
        ax.plot([i, i], [c.low, c.high], color=color, linewidth=1, alpha=alpha)
        # body
        body_bottom = min(c.open, c.close)
        body_height = abs(c.close - c.open) or 0.01  # avoid zero-height body
        ax.add_patch(
            plt.Rectangle((i - 0.3, body_bottom), 0.6, body_height, color=color, alpha=alpha)
        )

    ax.set_xlim(-1, len(all_candles))
    labels = [c.bucket_start.strftime("%H:%M") for c in all_candles]
    step = max(1, len(labels) // 12)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)], rotation=45, ha="right")

    last = all_candles[-1]
    ax.set_title(
        f"XAU/USD — {CANDLE_SECONDS}s candles   last: {last.close:.2f}   "
        f"({'forming' if current else 'closed'})"
    )
    ax.set_ylabel("Price (USD)")


def main():
    if not API_KEY:
        print(
            "Set TWELVE_DATA_API_KEY first (see script docstring for how). "
            "Free key: https://twelvedata.com/pricing"
        )
        sys.exit(1)

    aggregator = TickAggregator(interval_seconds=CANDLE_SECONDS)
    closed_candles: deque[Candle] = deque(maxlen=MAX_CANDLES)

    fig, ax = plt.subplots(figsize=(12, 6))

    def update(_frame):
        result = fetch_price()
        if result is None:
            return
        ts, price = result
        closed = aggregator.add_tick(ts, price)
        if closed is not None:
            closed_candles.append(closed)
        draw_candles(ax, list(closed_candles), aggregator.peek_current())

    ani = animation.FuncAnimation(
        fig, update, interval=POLL_SECONDS * 1000, cache_frame_data=False
    )
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
