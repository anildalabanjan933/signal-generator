# =================================================
# strategy.py - futures_2h_30m
# 30M Entry Signal Generator
# Trend direction from 2H candles
# Entry signals from 30M candles
# =================================================

import pandas as pd


def generate_signals(df_30m: pd.DataFrame, trend_aligned: pd.Series) -> pd.DataFrame:
    """
    Generate entry and exit signals on the 30M timeframe.

    ENTRY RULES:
        BUY  : 2H trend = bull
               AND 30M EMA50 > EMA200
               AND RSI crosses above 50 (prev < 50, curr >= 50)

        SELL : 2H trend = bear
               AND 30M EMA50 < EMA200
               AND RSI crosses below 50 (prev > 50, curr <= 50)

    EXIT RULES (Supertrend Flip):
        EXIT_BUY  : Supertrend flips from bull -> bear
        EXIT_SELL : Supertrend flips from bear -> bull

    Signal column values (uppercase — must match live_runner.py):
        "BUY"      - enter long
        "SELL"     - enter short
        "EXIT_BUY" - close long position
        "EXIT_SELL"- close short position
        None       - no action
    """

    df = df_30m.copy()

    # 2H trend alignment
    # Renamed from trend_4h to trend_2h to match this strategy
    df["trend_2h"] = trend_aligned

    # =================================================
    # RSI CROSS DETECTION
    # =================================================
    rsi_prev = df["rsi"].shift(1)

    df["rsi_cross_above_50"] = (
        (rsi_prev < 50) &
        (df["rsi"] >= 50)
    )

    df["rsi_cross_below_50"] = (
        (rsi_prev > 50) &
        (df["rsi"] <= 50)
    )

    # =================================================
    # SUPERTREND FLIP DETECTION
    # =================================================
    st_prev = df["supertrend_bull"].shift(1)

    # Bull -> Bear flip
    df["st_flip_bear"] = (
        (st_prev == True) &
        (df["supertrend_bull"] == False)
    )

    # Bear -> Bull flip
    df["st_flip_bull"] = (
        (st_prev == False) &
        (df["supertrend_bull"] == True)
    )

    # =================================================
    # ENTRY CONDITIONS
    # =================================================
    buy_condition = (
        (df["trend_2h"] == "bull") &
        (df["ema_fast"] > df["ema_slow"]) &
        (df["rsi_cross_above_50"] == True)
    )

    sell_condition = (
        (df["trend_2h"] == "bear") &
        (df["ema_fast"] < df["ema_slow"]) &
        (df["rsi_cross_below_50"] == True)
    )

    # =================================================
    # EXIT CONDITIONS
    # =================================================
    exit_buy_condition = (
        df["st_flip_bear"] == True
    )

    exit_sell_condition = (
        df["st_flip_bull"] == True
    )

    # =================================================
    # ASSIGN ALL SIGNALS INTO SINGLE signal COLUMN
    # Order matters: entry signals written first,
    # exit signals written second so exits do not
    # overwrite entries on the same bar.
    # live_runner.py reads only the signal column.
    # =================================================
    df["signal"] = None

    df.loc[buy_condition,       "signal"] = "BUY"
    df.loc[sell_condition,      "signal"] = "SELL"
    df.loc[exit_buy_condition,  "signal"] = "EXIT_BUY"
    df.loc[exit_sell_condition, "signal"] = "EXIT_SELL"

    return df
