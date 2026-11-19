"""
Pulls real historical XAU/USD data from Twelve Data and saves it in the
exact CSV format backtest_thresholds.py and run_example.py expect
(timestamp,open,high,low,close).

Uses the same TWELVE_DATA_API_KEY you already set up for the live charts.

Usage:
    pip install requests pandas
    export TWELVE_DATA_API_KEY=your_key_here
    python pull_historical_data.py

Produces:
    historical_daily.csv     — daily bars, as far back as your plan allows
    historical_intraday.csv  — 1-minute bars, last N days (see below)

IMPORTANT — free-tier limitations:
Twelve Data's free plan restricts both how far back intraday (1-minute)
history goes and how many requests you can make per minute (8/min,
800/day as of writing — check twelvedata.com/pricing, this can change).
This script is written to degrade gracefully: if a request for a given
date range fails or comes back empty (common on the free tier for
older intraday data), it prints exactly what happened and moves on
rather than crashing, so you end up with whatever history your plan
actually supports rather than nothing at all.

If you need deeper intraday history than the free tier provides, either
upgrade the plan or switch to a vendor with a generous historical
intraday allowance (e.g. Databento, Polygon.io) — the CSV format this
script produces would stay the same either way.
"""

from __future__ import annotations
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd

API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
SYMBOL = "XAU/USD"
BASE_URL = "https://api.twelvedata.com/time_series"

# Free tier: 8 requests/minute. Leave margin.
SECONDS_BETWEEN_REQUESTS = 8

# 1-minute bars: max ~5000 rows per call (~3.5 days). Chunk backward from
# today in ~3-day windows for INTRADAY_DAYS total days of history.
INTRADAY_DAYS = 10
INTRADAY_CHUNK_DAYS = 3

DAILY_OUTPUTSIZE = 500  # ~2 years of daily bars if your plan allows that far back


def fetch_time_series(interval: str, **params) -> pd.DataFrame | None:
    query = {"symbol": SYMBOL, "interval": interval, "apikey": API_KEY, "format": "JSON", **params}
    try:
        resp = requests.get(BASE_URL, params=query, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"  [error] Request failed: {e}")
        return None

    if data.get("status") == "error" or "values" not in data:
        print(f"  [error] API returned: {data.get('message', data)}")
        return None

    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].astype(float)
    return df


def pull_daily() -> pd.DataFrame:
    print(f"Fetching daily history (outputsize={DAILY_OUTPUTSIZE})...")
    df = fetch_time_series("1day", outputsize=DAILY_OUTPUTSIZE)
    if df is None:
        print("  Daily fetch failed entirely — check your API key and symbol access.")
        return pd.DataFrame()
    print(f"  Got {len(df)} daily bars: {df.index[0].date()} to {df.index[-1].date()}")
    return df


def pull_intraday() -> pd.DataFrame:
    print(f"Fetching last {INTRADAY_DAYS} days of 1-minute bars "
          f"(in {INTRADAY_CHUNK_DAYS}-day chunks, respecting rate limits)...")

    chunks = []
    end = datetime.now(timezone.utc)
    days_remaining = INTRADAY_DAYS

    while days_remaining > 0:
        chunk_days = min(INTRADAY_CHUNK_DAYS, days_remaining)
        start = end - timedelta(days=chunk_days)

        print(f"  Requesting {start.date()} to {end.date()}...")
        df_chunk = fetch_time_series(
            "1min",
            start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
            end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
        )
        if df_chunk is not None and not df_chunk.empty:
            chunks.append(df_chunk)
            print(f"    -> {len(df_chunk)} bars")
        else:
            print(f"    -> no data for this range (may be outside free-tier intraday history)")

        end = start
        days_remaining -= chunk_days
        time.sleep(SECONDS_BETWEEN_REQUESTS)

    if not chunks:
        print("  No intraday data retrieved at all.")
        return pd.DataFrame()

    combined = pd.concat(chunks).sort_index()
    combined = combined[~combined.index.duplicated(keep="first")]
    print(f"  Total intraday bars: {len(combined)} "
          f"({combined.index[0]} to {combined.index[-1]})")
    return combined


def main():
    if not API_KEY:
        print("Set TWELVE_DATA_API_KEY first. Free key: https://twelvedata.com/pricing")
        sys.exit(1)

    daily = pull_daily()
    if not daily.empty:
        daily.to_csv("historical_daily.csv", index_label="timestamp")
        print(f"Wrote historical_daily.csv ({len(daily)} rows)")

    time.sleep(SECONDS_BETWEEN_REQUESTS)

    intraday = pull_intraday()
    if not intraday.empty:
        intraday.to_csv("historical_intraday.csv", index_label="timestamp")
        print(f"Wrote historical_intraday.csv ({len(intraday)} rows)")

    if daily.empty and intraday.empty:
        print("\nNothing was retrieved — check your API key, plan limits, and symbol access.")
        sys.exit(1)

    print(
        "\nNext step: python backtest_thresholds.py historical_daily.csv historical_intraday.csv"
    )


if __name__ == "__main__":
    main()
