# =================================================
# indicators.py - Technical Indicators
# EMA, RSI, ADX, ATR, Supertrend
#
# FIXES APPLIED:
#   FIX7 - All config key names corrected from uppercase
#          to lowercase to match config.build_params() output.
#          EMA_FAST       → ema_fast
#          EMA_SLOW       → ema_slow
#          RSI_PERIOD     → rsi_period
#          ADX_PERIOD     → adx_period
#          SUPERTREND_ATR_PERIOD → supertrend_period
#          SUPERTREND_MULTIPLIER → supertrend_multiplier
#
#   FIX8 - SUPERTREND_ATR_PERIOD key removed entirely.
#          It did not exist in config.py or build_params().
#          Replaced with correct key: supertrend_period.
#
#   FIX9 - ATR column now exposed in add_all_indicators() output.
#          Previously computed only inside calculate_supertrend()
#          and discarded. Backtest engine needs atr column for:
#            - SL/TP distance calculation (atr_sl_tp mode)
#            - ema200_proximity filter
#            - trailing stop distance
#          calculate_atr() added as standalone function.
#
#   FIX10 - rsi_prev column added in add_all_indicators().
#           Entry condition is RSI crossing above/below 50.
#           Crossover requires current vs previous bar comparison.
#           rsi_prev = rsi.shift(1) added explicitly here so
#           strategy layer does not recompute it inconsistently.
#
#   I1  - supertrend_bull_prev shift NaN coercion fixed.
#         shift(1) on bool Series introduces NaN at row 0,
#         forcing pandas to upcast bool → object/float64.
#         Fixed with .fillna(True).astype(bool).
#
#   I2  - calculate_supertrend() loop rewritten using numpy arrays.
#         .iloc[i]= setter inside loop raises ChainedAssignmentError
#         in pandas >= 2.0. All loop work now done on raw numpy
#         arrays; results wrapped back into pd.Series at the end.
#
#   I3  - Docstring corrected: ATR period for standalone atr column
#         (atr_period=14) and ATR period inside Supertrend
#         (supertrend_period=10) are different by design.
#         Previous docstring incorrectly stated they were the same.
#
#   I4  - add_indicators() renamed to add_all_indicators().
#         backtest_engine.py calls add_all_indicators() but the
#         function was named add_indicators() — NameError at runtime.
#
#   I5  - ema50 / ema200 column names added as aliases.
#         backtest_engine._build_merged_df() expects columns named
#         ema50 and ema200 from each TF DataFrame before merge.
#         add_all_indicators() was writing ema_fast / ema_slow only.
#         Both sets of names now written so merge suffixing works:
#           ema_fast  → kept for signal_engine.py compatibility
#           ema_slow  → kept for signal_engine.py compatibility
#           ema50     → required by _build_merged_df() / _trend_is_bullish()
#           ema200    → required by _build_merged_df() / _trend_is_bearish()
#
#   I6  - supertrend_signal column added.
#         backtest_engine._build_merged_df() carries supertrend_signal
#         from trend TF and suffixes it to supertrend_signal_trend.
#         Previously only supertrend_bull (bool) was written.
#         supertrend_signal now written as "bullish"/"bearish" string
#         so _supertrend_is_bullish() / _supertrend_is_bearish()
#         string-path works correctly.
# =================================================

import pandas as pd
import numpy as np


# -------------------------------------------------
# EMA
# -------------------------------------------------
def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average.

    Args:
        series : Price series (typically close)
        period : EMA period

    Returns:
        pd.Series of EMA values
    """
    return series.ewm(span=period, adjust=False).mean()


# -------------------------------------------------
# RSI
# -------------------------------------------------
def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index using Wilder's smoothing method.

    Args:
        series : Price series (typically close)
        period : RSI period (default 14)

    Returns:
        pd.Series of RSI values (0-100)
    """
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


# -------------------------------------------------
# ADX
# -------------------------------------------------
def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Average Directional Index (ADX).
    Measures trend strength regardless of direction.

    Args:
        high   : High price series
        low    : Low price series
        close  : Close price series
        period : ADX smoothing period (default 14)

    Returns:
        pd.Series of ADX values
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    up_move   = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm  = np.where((up_move > down_move) & (up_move > 0),   up_move,   0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_series  = pd.Series(plus_dm,  index=close.index)
    minus_dm_series = pd.Series(minus_dm, index=close.index)

    atr_smooth      = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di_smooth  = plus_dm_series.ewm(alpha=1.0 / period, adjust=False).mean()
    minus_di_smooth = minus_dm_series.ewm(alpha=1.0 / period, adjust=False).mean()

    plus_di  = 100 * plus_di_smooth  / atr_smooth.replace(0, np.nan)
    minus_di = 100 * minus_di_smooth / atr_smooth.replace(0, np.nan)

    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()

    return adx.fillna(0)


# -------------------------------------------------
# ATR  (standalone)
# -------------------------------------------------
def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Average True Range using Wilder's smoothing.

    Args:
        high   : High price series
        low    : Low price series
        close  : Close price series
        period : ATR period (default 14)

    Returns:
        pd.Series of ATR values
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# -------------------------------------------------
# SUPERTREND
# -------------------------------------------------
def calculate_supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int   = 10,
    multiplier: float = 3.0
) -> pd.DataFrame:
    """
    Supertrend indicator.

    Args:
        high       : High price series
        low        : Low price series
        close      : Close price series
        atr_period : ATR period used internally (default 10)
        multiplier : ATR multiplier (default 3.0)

    Returns:
        pd.DataFrame with columns:
            supertrend        : Supertrend line value
            supertrend_bull   : True when trend is bullish
            supertrend_signal : 'bullish' or 'bearish' string
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1.0 / atr_period, adjust=False).mean()

    hl2         = (high + low) / 2
    basic_upper = (hl2 + (multiplier * atr)).to_numpy()
    basic_lower = (hl2 - (multiplier * atr)).to_numpy()

    n         = len(close)
    close_arr = close.to_numpy()
    fu        = basic_upper.copy()
    fl        = basic_lower.copy()
    st        = np.full(n, np.nan)
    bull      = np.ones(n, dtype=bool)

    for i in range(1, n):
        fu[i] = (
            basic_upper[i]
            if (basic_upper[i] < fu[i-1] or close_arr[i-1] > fu[i-1])
            else fu[i-1]
        )
        fl[i] = (
            basic_lower[i]
            if (basic_lower[i] > fl[i-1] or close_arr[i-1] < fl[i-1])
            else fl[i-1]
        )

        if st[i-1] == fu[i-1]:
            if close_arr[i] <= fu[i]:
                st[i]   = fu[i]
                bull[i] = False
            else:
                st[i]   = fl[i]
                bull[i] = True
        else:
            if close_arr[i] >= fl[i]:
                st[i]   = fl[i]
                bull[i] = True
            else:
                st[i]   = fu[i]
                bull[i] = False

    st[0]   = fl[0]
    bull[0] = True

    # I6: supertrend_signal as string for _supertrend_is_bullish/bearish()
    signal = pd.Series(
        np.where(bull, "bullish", "bearish"),
        index=close.index
    )

    return pd.DataFrame({
        "supertrend"       : pd.Series(st,   index=close.index),
        "supertrend_bull"  : pd.Series(bull, index=close.index),
        "supertrend_signal": signal,
    })


# -------------------------------------------------
# APPLY ALL INDICATORS TO DATAFRAME
# -------------------------------------------------
def add_all_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """
    Add all required indicators to a candle DataFrame.

    I4: Renamed from add_indicators() to add_all_indicators()
        to match the call in backtest_engine.py.

    I5: ema50 / ema200 aliases added alongside ema_fast / ema_slow.
        backtest_engine._build_merged_df() expects ema50 and ema200
        column names before merge suffixing.

    I6: supertrend_signal string column added.
        backtest_engine reads supertrend_signal_trend and
        supertrend_signal_trigger after merge.

    Args:
        df     : OHLCV DataFrame. Must have: open, high, low, close, volume
        params : Flat params dict from config.build_params()

    Returns:
        DataFrame with added columns:
            ema_fast             : Fast EMA (ema_fast period)
            ema_slow             : Slow EMA (ema_slow period)
            ema50                : Alias for ema_fast (I5)
            ema200               : Alias for ema_slow (I5)
            rsi                  : RSI value
            rsi_prev             : Previous bar RSI (for crossover)
            adx                  : ADX value
            atr                  : ATR value (atr_period)
            supertrend           : Supertrend line value
            supertrend_bull      : True when bullish
            supertrend_bull_prev : Previous bar direction (bool)
            supertrend_signal    : 'bullish' or 'bearish' string (I6)
    """
    df = df.copy()

    # ── EMA ──────────────────────────────────────────────────────
    df["ema_fast"] = calculate_ema(df["close"], params["ema_fast"])
    df["ema_slow"] = calculate_ema(df["close"], params["ema_slow"])

    # I5: aliases required by backtest_engine merge logic
    df["ema50"]  = df["ema_fast"]
    df["ema200"] = df["ema_slow"]

    # ── RSI ──────────────────────────────────────────────────────
    df["rsi"]      = calculate_rsi(df["close"], params["rsi_period"])
    df["rsi_prev"] = df["rsi"].shift(1).fillna(50)

    # ── ADX ──────────────────────────────────────────────────────
    df["adx"] = calculate_adx(
        df["high"], df["low"], df["close"],
        params["adx_period"]
    )

    # ── ATR ──────────────────────────────────────────────────────
    df["atr"] = calculate_atr(
        df["high"], df["low"], df["close"],
        params["atr_period"]
    )

    # ── Supertrend ───────────────────────────────────────────────
    st = calculate_supertrend(
        df["high"], df["low"], df["close"],
        atr_period = params["supertrend_period"],
        multiplier = params["supertrend_multiplier"]
    )
    df["supertrend"]           = st["supertrend"]
    df["supertrend_bull"]      = st["supertrend_bull"]
    df["supertrend_signal"]    = st["supertrend_signal"]                          # I6
    df["supertrend_bull_prev"] = df["supertrend_bull"].shift(1).fillna(True).astype(bool)  # I1

    return df
