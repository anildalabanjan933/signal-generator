# =================================================
# filters.py - 4H Trend Filter
# Checks: EMA50 > EMA200, Supertrend, ADX > 20
# =================================================

import pandas as pd


def get_4h_trend(df_4h: pd.DataFrame, adx_threshold: float = 20.0) -> pd.Series:
    """
    Compute 4H trend direction for each candle.

    Rules:
        BULL : EMA50 > EMA200  AND  Supertrend bullish  AND  ADX > threshold
        BEAR : EMA50 < EMA200  AND  Supertrend bearish  AND  ADX > threshold
        NONE : ADX too weak or EMAs conflicting

    Args:
        df_4h         : 4H DataFrame with indicators already applied
        adx_threshold : Minimum ADX value for valid trend (default 20)

    Returns:
        pd.Series with values: 'bull', 'bear', or 'none'
        Indexed by the 4H candle timestamps
    """
    conditions_bull = (
        (df_4h["ema_fast"] > df_4h["ema_slow"]) &
        (df_4h["supertrend_bull"] == True) &
        (df_4h["adx"] > adx_threshold)
    )

    conditions_bear = (
        (df_4h["ema_fast"] < df_4h["ema_slow"]) &
        (df_4h["supertrend_bull"] == False) &
        (df_4h["adx"] > adx_threshold)
    )

    trend = pd.Series("none", index=df_4h.index)
    trend[conditions_bull] = "bull"
    trend[conditions_bear] = "bear"

    return trend


def align_4h_trend_to_1h(
    trend_4h: pd.Series,
    df_1h: pd.DataFrame
) -> pd.Series:
    """
    Align 4H trend labels to 1H candle timestamps using forward-fill.
    Each 1H candle gets the trend of the most recently completed 4H candle.

    Args:
        trend_4h : pd.Series of trend labels indexed by 4H timestamps
        df_1h    : 1H DataFrame indexed by 1H timestamps

    Returns:
        pd.Series of trend labels aligned to 1H index
    """
    # Reindex to 1H timestamps, forward-fill 4H trend into each 1H candle
    aligned = trend_4h.reindex(
        trend_4h.index.union(df_1h.index)
    ).ffill().reindex(df_1h.index)

    return aligned.fillna("none")
