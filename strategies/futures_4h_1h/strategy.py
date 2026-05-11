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

    Args:
        df_1h          : 1H DataFrame with indicators applied
        trend_aligned  : 4H trend labels aligned to 1H index ('bull'/'bear'/'none')

    Returns:
        DataFrame with added columns:
            signal      : 'buy', 'sell', or None
            exit_signal : 'exit_buy', 'exit_sell', or None
    """
    df = df_1h.copy()
    df["trend_4h"] = trend_aligned

    # RSI cross detection
    rsi_prev = df["rsi"].shift(1)
    df["rsi_cross_above_50"] = (rsi_prev < 50) & (df["rsi"] >= 50)
    df["rsi_cross_below_50"] = (rsi_prev > 50) & (df["rsi"] <= 50)

    # Supertrend flip detection
    st_prev = df["supertrend_bull"].shift(1)
    df["st_flip_bear"] = (st_prev == True)  & (df["supertrend_bull"] == False)  # bull->bear
    df["st_flip_bull"] = (st_prev == False) & (df["supertrend_bull"] == True)   # bear->bull

    # BUY signal
    buy_condition = (
        (df["trend_4h"] == "bull") &
        (df["ema_fast"] > df["ema_slow"]) &
        (df["rsi_cross_above_50"] == True)
    )

    # SELL signal
    sell_condition = (
        (df["trend_4h"] == "bear") &
        (df["ema_fast"] < df["ema_slow"]) &
        (df["rsi_cross_below_50"] == True)
    )

    # EXIT signals (Supertrend flip)
    exit_buy_condition  = df["st_flip_bear"] == True   # Exit long
    exit_sell_condition = df["st_flip_bull"] == True   # Exit short

    # Assign signals
    df["signal"] = None
    df.loc[buy_condition,  "signal"] = "buy"
    df.loc[sell_condition, "signal"] = "sell"

    df["exit_signal"] = None
    df.loc[exit_buy_condition,  "exit_signal"] = "exit_buy"
    df.loc[exit_sell_condition, "exit_signal"] = "exit_sell"

    return df
