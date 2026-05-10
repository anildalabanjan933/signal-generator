# =================================================
# signal_generator.py - 1H Entry Signal Generator
# Detects BUY / SELL entries and Supertrend flip exits
#
# FIXES APPLIED:
#   S1  - rsi_prev no longer recomputed locally via shift(1).
#         indicators.py FIX10 writes df["rsi_prev"] explicitly.
#         signal_generator now reads that column directly.
#         Prevents silent divergence if RSI smoothing changes
#         in indicators.py.
#
#   S2  - supertrend_bull_prev no longer recomputed locally.
#         indicators.py FIX10 writes df["supertrend_bull_prev"]
#         with fillna(True).astype(bool) (I1 fix).
#         signal_generator reads that column directly.
#
#   S3  - params argument added to generate_signals().
#         RSI mid-level threshold now comes from
#         params.get("rsi_mid_level", 50) — tunable by optimizer.
#         ADX filter now applied when use_trend_strength_filter
#         is True, using adx_min_threshold from params.
#
#   S4  - Boolean comparisons cleaned up.
#         == True / == False on boolean Series replaced with
#         direct boolean usage to avoid dtype-unsafe comparisons
#         when column is object dtype.
#
#   S5  - File renamed from signal_engine.py to
#         signal_generator.py to match project tracker.
# =================================================

import pandas as pd


def generate_signals(
    df_1h: pd.DataFrame,
    trend_aligned: pd.Series,
    params: dict
) -> pd.DataFrame:
    """
    Generate entry and exit signals on the 1H timeframe.

    ENTRY RULES:
        BUY  : 4H trend = bull
               AND 1H EMA50 > EMA200
               AND RSI crosses above rsi_mid_level (default 50)
               AND ADX >= adx_min_threshold (if use_trend_strength_filter)

        SELL : 4H trend = bear
               AND 1H EMA50 < EMA200
               AND RSI crosses below rsi_mid_level (default 50)
               AND ADX >= adx_min_threshold (if use_trend_strength_filter)

    EXIT RULES (Supertrend Flip):
        BUY EXIT  : Supertrend flips from bull -> bear
        SELL EXIT : Supertrend flips from bear -> bull

    Args:
        df_1h          : 1H DataFrame with indicators applied via
                         indicators.add_indicators(). Must contain:
                         ema_fast, ema_slow, rsi, rsi_prev,
                         adx, supertrend_bull, supertrend_bull_prev.
        trend_aligned  : 4H trend labels aligned to 1H index
                         ('bull' / 'bear' / 'none')
        params         : Flat params dict from config.build_params().
                         Keys used:
                           rsi_mid_level           (default 50)
                           adx_min_threshold       (default 20)
                           use_trend_strength_filter (default True)

    Returns:
        DataFrame with added columns:
            signal      : 'buy', 'sell', or None
            exit_signal : 'exit_buy', 'exit_sell', or None

    FIXES:
        S1 - rsi_prev read from df column (set by indicators FIX10),
             not recomputed locally.
        S2 - supertrend_bull_prev read from df column (set by
             indicators FIX10 + I1), not recomputed locally.
        S3 - params argument added; RSI threshold and ADX filter
             now driven by params instead of hardcoded values.
        S4 - == True / == False removed; direct boolean used.
        S5 - File renamed signal_engine.py → signal_generator.py.
    """
    df = df_1h.copy()
    df["trend_4h"] = trend_aligned

    # ── Params ──────────────────────────────────────────────
    # S3: all thresholds from params, not hardcoded
    rsi_mid  = params.get("rsi_mid_level", 50)
    adx_min  = params.get("adx_min_threshold", 20)
    use_adx  = params.get("use_trend_strength_filter", True)

    # ── RSI cross detection ─────────────────────────────────
    # S1: read rsi_prev from df (written by indicators.py FIX10)
    #     not recomputed here via shift(1)
    df["rsi_cross_above"] = (df["rsi_prev"] < rsi_mid) & (df["rsi"] >= rsi_mid)
    df["rsi_cross_below"] = (df["rsi_prev"] > rsi_mid) & (df["rsi"] <= rsi_mid)

    # ── Supertrend flip detection ───────────────────────────
    # S2: read supertrend_bull_prev from df (written by indicators.py FIX10+I1)
    #     not recomputed here via shift(1)
    df["st_flip_bear"] = df["supertrend_bull_prev"] & ~df["supertrend_bull"]   # bull->bear
    df["st_flip_bull"] = ~df["supertrend_bull_prev"] & df["supertrend_bull"]   # bear->bull

    # ── BUY condition ───────────────────────────────────────
    buy_condition = (
        (df["trend_4h"] == "bull") &
        (df["ema_fast"] > df["ema_slow"]) &
        df["rsi_cross_above"]                          # S4: no == True
    )

    # ── SELL condition ──────────────────────────────────────
    sell_condition = (
        (df["trend_4h"] == "bear") &
        (df["ema_fast"] < df["ema_slow"]) &
        df["rsi_cross_below"]                          # S4: no == True
    )

    # ── ADX filter ──────────────────────────────────────────
    # S3: apply ADX filter only when use_trend_strength_filter is True
    if use_adx:
        adx_ok         = df["adx"] >= adx_min
        buy_condition  = buy_condition  & adx_ok
        sell_condition = sell_condition & adx_ok

    # ── EXIT conditions ─────────────────────────────────────
    # S4: direct boolean — no == True
    exit_buy_condition  = df["st_flip_bear"]   # Exit long
    exit_sell_condition = df["st_flip_bull"]   # Exit short

    # ── Assign signals ──────────────────────────────────────
    df["signal"] = None
    df.loc[buy_condition,  "signal"] = "buy"
    df.loc[sell_condition, "signal"] = "sell"

    df["exit_signal"] = None
    df.loc[exit_buy_condition,  "exit_signal"] = "exit_buy"
    df.loc[exit_sell_condition, "exit_signal"] = "exit_sell"

    return df
