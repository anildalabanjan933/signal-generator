# =================================================
# strategy.py - 1H Entry Signal Generator
# Detects BUY / SELL entries and Supertrend flip exits
# =================================================

import pandas as pd


def generate_signals(df_1h: pd.DataFrame, trend_aligned: pd.Series) -> pd.DataFrame:
    """
    Generate entry and exit signals on the 1H timeframe.

    ENTRY RULES:
        BUY  : 4H trend = bull
               AND 1H EMA50 > EMA200
               AND RSI crosses above 50 (prev < 50, curr >= 50)

        SELL : 4H trend = bear
               AND 1H EMA50 < EMA200
               AND RSI crosses below 50 (prev > 50, curr <= 50)

    EXIT RULES (Supertrend Flip):
        BUY EXIT  : Supertrend flips from bull -> bear
        SELL EXIT : Supertrend flips from bear -> bull
    """

    df = df_1h.copy()

    # 4H trend alignment
    df["trend_4h"] = trend_aligned

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

    # Bull -> Bear
    df["st_flip_bear"] = (
        (st_prev == True) &
        (df["supertrend_bull"] == False)
    )

    # Bear -> Bull
    df["st_flip_bull"] = (
        (st_prev == False) &
        (df["supertrend_bull"] == True)
    )

    # =================================================
    # BUY SIGNAL
    # =================================================
    buy_condition = (
        (df["trend_4h"] == "bull") &
        (df["ema_fast"] > df["ema_slow"]) &
        (df["rsi_cross_above_50"] == True)
    )

    # =================================================
    # SELL SIGNAL
    # =================================================
    sell_condition = (
        (df["trend_4h"] == "bear") &
        (df["ema_fast"] < df["ema_slow"]) &
        (df["rsi_cross_below_50"] == True)
    )

    # =================================================
    # EXIT SIGNALS
    # =================================================
    exit_buy_condition = (
        df["st_flip_bear"] == True
    )

    exit_sell_condition = (
        df["st_flip_bull"] == True
    )

    # =================================================
    # ASSIGN SIGNALS
    # =================================================
    df["signal"] = None

    df.loc[
        buy_condition,
        "signal"
    ] = "buy"

    df.loc[
        sell_condition,
        "signal"
    ] = "sell"

    # =================================================
    # ASSIGN EXIT SIGNALS
    # =================================================
    df["exit_signal"] = None

    df.loc[
        exit_buy_condition,
        "exit_signal"
    ] = "exit_buy"

    df.loc[
        exit_sell_condition,
        "exit_signal"
    ] = "exit_sell"

    return df