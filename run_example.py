"""
Example: running the full detector stack on a 1-minute OHLCV dataframe.

Usage:
    pip install pandas numpy pytz
    python run_example.py path/to/your_1min_data.csv

Expected CSV columns: timestamp, open, high, low, close (volume optional).
`timestamp` should be ISO 8601 and either already UTC or include an offset.
"""

import sys
import pandas as pd

from engine.core import (
    to_ny_time,
    key_time_window_mask,
    ny_lunch_no_trade_mask,
    session_tag,
    swing_highs_lows,
    relative_equal_levels,
)
from engine.fair_value_gaps import detect_fair_value_gaps, mark_fill_status
from engine.order_blocks import detect_displacement, detect_order_blocks, annotate_order_blocks_with_fvg
from engine.power_three import daily_bias_from_range, opening_range_projection
from engine.gaps import (
    opening_range_gap, grade_gap_size, seventy_percent_rule_check,
    first_presented_fvg, classify_gap_fill_behavior, detect_stacked_fvgs,
)
from engine.sessions_extended import (
    macro_time_window_mask, silver_bullet_window_mask, final_hour_macro_mask,
)
from engine.order_block_extras import mean_threshold, detect_mitigation_blocks, detect_rejection_blocks
from engine.range_analysis import (
    inside_day_and_compression, large_range_day_opening_position,
    classify_swing_tiers, standard_deviation_projection,
)


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.set_index("timestamp")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].sort_index()


def main():
    if len(sys.argv) != 2:
        print("Usage: python run_example.py path/to/data.csv")
        sys.exit(1)

    df = load_data(sys.argv[1])
    print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")

    # --- Session / timing tags -------------------------------------------------
    df_ny = to_ny_time(df)
    df_ny["session"] = session_tag(df)
    df_ny["in_key_window"] = key_time_window_mask(df)
    df_ny["no_trade_lunch"] = ny_lunch_no_trade_mask(df)

    # --- Swing points ------------------------------------------------------------
    swings = swing_highs_lows(df, left=1, right=1)
    n_highs = swings["swing_high"].sum()
    n_lows = swings["swing_low"].sum()
    print(f"Found {n_highs} swing highs, {n_lows} swing lows")

    # --- Relative equal highs/lows (priming) -------------------------------------
    equal_levels = relative_equal_levels(df, swings, tolerance_pct=0.0007, before_time="08:30")
    print(f"Found {len(equal_levels)} relative-equal-high/low setups formed before 08:30")
    for lvl in equal_levels[:5]:
        print(f"  {lvl.kind}: {lvl.first_price:.2f} -> {lvl.second_price:.2f} "
              f"(confirmed {lvl.formed_before})")

    # --- Fair value gaps -----------------------------------------------------------
    gaps = detect_fair_value_gaps(df)
    gaps = mark_fill_status(df, gaps)
    print(f"Found {len(gaps)} fair value gaps ({sum(g.filled for g in gaps)} filled so far)")

    # --- Displacement + order blocks ------------------------------------------------
    legs = detect_displacement(df, lookback=20, min_multiple=2.5)
    blocks = detect_order_blocks(df, legs)
    blocks = annotate_order_blocks_with_fvg(blocks, gaps)
    print(f"Found {len(legs)} displacement legs -> {len(blocks)} order blocks "
          f"({sum(b.has_fvg_nearby for b in blocks)} with a nearby FVG)")

    # --- Daily bias (needs a daily-resampled frame) ---------------------------------
    daily = df.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    biases = daily_bias_from_range(daily, lookback_days=10)
    if biases:
        latest = biases[-1]
        print(f"Latest daily bias ({latest.date.date()}): {latest.bias} "
              f"({latest.close_position}, eq={latest.equilibrium:.2f})")

        # Example opening range projection using today's open and the day's
        # high as a stand-in "manipulation extreme" — in practice you'd
        # identify the actual Judas-swing extreme intraday, not just the
        # day's high, but this shows the calculation shape.
        today = daily.iloc[-1]
        proj = opening_range_projection(
            open_price=today["open"],
            manipulation_extreme=today["high"] if latest.bias == "bearish" else today["low"],
            bias=latest.bias if latest.bias != "unclear" else "bullish",
        )
        print(f"Opening range projection example: {proj}")

    # --- Opening Range Gap (needs prior settlement + today's open) -----------------
    if len(daily) >= 2:
        prior_settlement = daily["close"].iloc[-2]
        todays_open = daily["open"].iloc[-1]
        org = opening_range_gap(prior_settlement, todays_open, daily.index[-1])
        print(f"\nOpening Range Gap: {org.low:.2f}-{org.high:.2f} "
              f"(size={org.size:.2f}, grade={grade_gap_size(org)}, midpoint={org.midpoint:.2f})")

        todays_intraday = df[df.index.normalize() == daily.index[-1].normalize()]
        if not todays_intraday.empty:
            touched = seventy_percent_rule_check(todays_intraday, org)
            print(f"70% Rule check (midpoint touched in first 30 min): {touched}")

            fpfvg = first_presented_fvg(todays_intraday)
            print(f"First presented FVG today: {'found' if fpfvg else 'none yet'}")

            fill_behavior = classify_gap_fill_behavior(todays_intraday, org)
            print(f"Gap fill behavior classification: {fill_behavior}")

    # --- Stacked FVGs (Model 2022) --------------------------------------------------
    stacked = detect_stacked_fvgs(gaps, max_distance_pct=0.01)
    print(f"\nStacked FVG (Model 2022) pairs found: {len(stacked)}")

    # --- Extended session windows ----------------------------------------------------
    print(f"\nBars in macro time windows: {macro_time_window_mask(df).sum()}")
    print(f"Bars in Silver Bullet window (10-11am): {silver_bullet_window_mask(df).sum()}")
    print(f"Bars in Final Hour macro (3-4pm): {final_hour_macro_mask(df).sum()}")

    # --- Order block extras: Mean Threshold, Mitigation Blocks, Rejection Blocks ----
    if blocks:
        example_block = blocks[0]
        print(f"\nMean Threshold of first order block: "
              f"{mean_threshold(example_block.open_price, df['close'].iloc[example_block.candle_idx]):.2f}")

    mitigation = detect_mitigation_blocks(df, consolidation_window=15, consolidation_range_pct=0.005)
    print(f"Mitigation block candidates found: {len(mitigation)} "
          f"(heuristic detector — tune thresholds before trusting these)")

    rejection = detect_rejection_blocks(df, wick_to_body_ratio=2.5)
    print(f"Rejection block candidates found: {len(rejection)}")

    # --- Range analysis: Inside Day / Compression, STL/ITL/LTL, Std Dev Projection --
    inside_results = inside_day_and_compression(daily, compression_lookback=3)
    if inside_results:
        latest_inside = inside_results[-1]
        print(f"\nLatest day range trend: {latest_inside.range_trend} "
              f"(inside day: {latest_inside.is_inside_day})")

    sh_points = [(i, df["high"].iloc[i]) for i in range(len(swings)) if swings["swing_high"].iloc[i]]
    sl_points = [(i, df["low"].iloc[i]) for i in range(len(swings)) if swings["swing_low"].iloc[i]]
    if sh_points and sl_points:
        classified = classify_swing_tiers(sh_points, sl_points)
        tier_counts = {}
        for c in classified:
            tier_counts[c.tier] = tier_counts.get(c.tier, 0) + 1
        print(f"Swing tier classification: {tier_counts}")

        if sh_points and sl_points:
            proj = standard_deviation_projection(sl_points[-1][1], sh_points[-1][1])
            print(f"Standard deviation projection from latest swing: {proj}")


if __name__ == "__main__":
    main()
