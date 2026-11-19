"""
ICT Wing — threshold calibration against real historical data.

IMPORTANT — what this script actually does:
This is a CALIBRATION tool, not a profit/loss backtester. Turning these
thresholds into a true backtest would require defining entries, exits,
stop placement, and position sizing — none of which have been specified
yet as a concrete trading model. What this script DOES do is honest and
useful on its own: it measures how the thresholds currently hard-coded
as guesses in the engine (the 40/200-handle ORG cutoffs, the displacement
multiple, the wick-to-body ratio) actually behave against YOUR
instrument's real historical distribution, so you can replace guesses
with data-driven choices.

Usage:
    pip install pandas numpy
    python backtest_thresholds.py daily_data.csv intraday_1min_data.csv

    daily_data.csv: columns timestamp,open,high,low,close (one row/day)
    intraday_1min_data.csv: columns timestamp,open,high,low,close (1-min bars)

Both should cover the same historical period for the same instrument.
"""

import sys
import numpy as np
import pandas as pd

from engine.core import to_ny_time, in_time_window, swing_highs_lows
from engine.gaps import opening_range_gap, grade_gap_size, seventy_percent_rule_check
from engine.order_blocks import detect_displacement, detect_order_blocks
from engine.order_block_extras import detect_rejection_blocks


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].sort_index()


def calibrate_gap_thresholds(df_daily: pd.DataFrame) -> None:
    """
    Computes the actual overnight-gap-size distribution for this
    instrument (close[t-1] to open[t]) and reports percentile-based
    threshold suggestions, instead of assuming the ~40/~200 handle
    figures from the NASDAQ-specific transcripts apply to your data.
    """
    gaps = (df_daily["open"] - df_daily["close"].shift(1)).abs().dropna()

    print("\n=== Gap Size Distribution (close[t-1] -> open[t]) ===")
    print(f"N days: {len(gaps)}")
    for pct in [10, 25, 50, 75, 90, 95]:
        print(f"  p{pct}: {np.percentile(gaps, pct):.2f}")

    suggested_anemic = np.percentile(gaps, 25)
    suggested_large = np.percentile(gaps, 90)
    print(f"\nSuggested 'anemic' threshold (25th pct): {suggested_anemic:.2f}")
    print(f"Suggested 'large' threshold (90th pct):  {suggested_large:.2f}")
    print("(vs. the NASDAQ-transcript guesses of ~40 and ~200 — compare and adjust)")


def backtest_seventy_percent_rule(df_daily: pd.DataFrame, df_intraday: pd.DataFrame) -> None:
    """
    For each day, builds the opening range gap from the daily data and
    checks whether the ORG midpoint was actually touched within the
    first 30 minutes of that day's intraday data — the concrete,
    checkable version of the '70% Rule' claim.
    """
    hits = 0
    total = 0

    for i in range(1, len(df_daily)):
        day = df_daily.index[i]
        prior_close = df_daily["close"].iloc[i - 1]
        today_open = df_daily["open"].iloc[i]
        org = opening_range_gap(prior_close, today_open, day)

        day_intraday = df_intraday[df_intraday.index.normalize() == day.normalize()]
        if day_intraday.empty:
            continue

        total += 1
        if seventy_percent_rule_check(day_intraday, org):
            hits += 1

    if total == 0:
        print("\n=== 70% Rule Backtest ===\nNo matching intraday days found — check your data covers the same dates.")
        return

    rate = hits / total * 100
    print(f"\n=== 70% Rule Backtest ===")
    print(f"Days tested: {total}")
    print(f"Midpoint touched within 30 min: {hits} ({rate:.1f}%)")
    print(f"(Transcript claim: ~70%. Your data says: {rate:.1f}%.)")


def sensitivity_sweep_displacement(df_intraday: pd.DataFrame, lookback: int = 20) -> None:
    """
    Sweeps the displacement 'min_multiple' threshold and reports how
    many displacement events per trading day each setting produces —
    lets you pick a threshold matching your desired signal frequency
    rather than the arbitrary 2.0/2.5 guesses used as defaults.
    """
    n_days = max(1, (df_intraday.index[-1] - df_intraday.index[0]).days)
    print("\n=== Displacement Threshold Sensitivity ===")
    print(f"(Data spans ~{n_days} days)")
    for multiple in [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        legs = detect_displacement(df_intraday, lookback=lookback, min_multiple=multiple)
        print(f"  min_multiple={multiple:>4}: {len(legs)} events total, "
              f"~{len(legs)/n_days:.1f} per day")


def sensitivity_sweep_rejection_blocks(df_intraday: pd.DataFrame) -> None:
    """Same idea for the wick-to-body ratio used to flag rejection blocks."""
    n_days = max(1, (df_intraday.index[-1] - df_intraday.index[0]).days)
    print("\n=== Rejection Block Wick-Ratio Sensitivity ===")
    for ratio in [1.5, 2.0, 2.5, 3.0, 4.0]:
        blocks = detect_rejection_blocks(df_intraday, wick_to_body_ratio=ratio)
        print(f"  wick_to_body_ratio={ratio:>4}: {len(blocks)} events total, "
              f"~{len(blocks)/n_days:.1f} per day")


def main():
    if len(sys.argv) != 3:
        print("Usage: python backtest_thresholds.py daily_data.csv intraday_1min_data.csv")
        sys.exit(1)

    df_daily = load_csv(sys.argv[1])
    df_intraday = load_csv(sys.argv[2])

    print(f"Loaded {len(df_daily)} daily bars, {len(df_intraday)} intraday bars.")

    calibrate_gap_thresholds(df_daily)
    backtest_seventy_percent_rule(df_daily, df_intraday)
    sensitivity_sweep_displacement(df_intraday)
    sensitivity_sweep_rejection_blocks(df_intraday)

    print(
        "\nNote: these are FREQUENCY and DISTRIBUTION statistics, not "
        "win-rate or profitability results. To go further, you'd need "
        "to define entry/exit/stop rules precisely enough to simulate "
        "trades — happy to help build that once those rules are pinned down."
    )


if __name__ == "__main__":
    main()
