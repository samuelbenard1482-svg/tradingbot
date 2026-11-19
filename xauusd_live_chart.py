"""
Live XAUUSD chart — pulls real spot-gold prices and plots them updating
in real time.

DATA SOURCE: Twelve Data (https://twelvedata.com)
  - Free tier: sign up at twelvedata.com, no credit card needed.
  - Free tier limits: 8 requests/minute, 800/day (as of writing — check
    their pricing page, this can change). This script polls on an
    interval you control (default 15s) to stay safely within that.
  - XAU/USD is listed under their "Forex" symbol list.

Why polling instead of a websocket: Twelve Data's free tier is REST-only;
websocket streaming requires a paid plan. Polling every 10-15s is still
"live" for anything except sub-minute scalping, and costs nothing.

ALTERNATIVE: OANDA's free practice-account API offers true tick-level
streaming for XAU_USD (their v20 REST streaming endpoint) if you want
lower latency — happy to build that version instead if this one doesn't
give you the update speed you need.

Usage:
    pip install requests matplotlib pandas
    export TWELVE_DATA_API_KEY=your_key_here
    python xauusd_live_chart.py
"""

from __future__ import annotations
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone

import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.animation as animation

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads a .env file in the current folder, if present
except ImportError:
    pass  # dotenv is optional — falls back to whatever's already in the environment

API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
SYMBOL = "XAU/USD"
POLL_SECONDS = 15          # respects free-tier rate limit (8 req/min)
MAX_POINTS = 240           # how many ticks to keep on screen (1 hour at 15s)
BASE_URL = "https://api.twelvedata.com/price"


def fetch_price() -> tuple[datetime, float] | None:
    """One REST call for the latest XAU/USD price. Returns (utc_time, price) or None on failure."""
    try:
        resp = requests.get(
            BASE_URL, params={"symbol": SYMBOL, "apikey": API_KEY}, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if "price" not in data:
            print(f"Unexpected response: {data}")
            return None
        return datetime.now(timezone.utc), float(data["price"])
    except requests.RequestException as e:
        print(f"Fetch error (will retry): {e}")
        return None


def main():
    if not API_KEY:
        print(
            "Set TWELVE_DATA_API_KEY first:\n"
            "  export TWELVE_DATA_API_KEY=your_key_here\n"
            "Get a free key at https://twelvedata.com/pricing (free tier, no card needed)."
        )
        sys.exit(1)

    times: deque = deque(maxlen=MAX_POINTS)
    prices: deque = deque(maxlen=MAX_POINTS)

    fig, ax = plt.subplots(figsize=(11, 5))
    line, = ax.plot([], [], color="#c9a227", linewidth=1.5)
    ax.set_title("XAU/USD — live (Twelve Data)")
    ax.set_ylabel("Price (USD)")

    # Explicitly tell matplotlib this x-axis holds dates/times. Without this,
    # feeding datetime objects into set_data() later (rather than at the
    # initial plot() call) can leave the axis treating them as huge plain
    # numbers (days-since-epoch), which makes new points invisible against
    # an absurdly wide auto-scaled range — the chart LOOKS frozen even
    # though it's still fetching and plotting correctly.
    ax.xaxis_date(tz=timezone.utc)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=timezone.utc))
    fig.autofmt_xdate()

    def update(_frame):
        result = fetch_price()
        if result is not None:
            ts, price = result
            times.append(ts)
            prices.append(price)
            line.set_data(list(times), list(prices))
            ax.relim()
            ax.autoscale_view()
            if prices:
                ax.set_title(f"XAU/USD — live   last: {prices[-1]:.2f}   {times[-1].strftime('%H:%M:%S UTC')}")
        return (line,)

    # interval is in milliseconds; matplotlib drives the polling cadence
    ani = animation.FuncAnimation(fig, update, interval=POLL_SECONDS * 1000, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
