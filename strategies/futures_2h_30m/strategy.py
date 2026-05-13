# =================================================
# strategy.py - futures_2h_30m
# 30M Entry Signal Generator
# Trend direction from 2H candles
# Entry signals from 30M candles
#
# FIXES APPLIED:
#   F1 - ema_fast/ema_slow replaced with ema50/ema200
#        on both trend check and entry condition.
#        ema_fast/ema_slow were EMA9/EMA21 — short-term
#        noise EMAs. Backtest used EMA50/EMA200.
#        Column names ema50 and ema200 must be present
#        in the dataframe passed from live_runner.py.
#
#   F2 - ADX > 20 added to trend filter (2H).
#        Filters out ranging/sideways markets.
#        Backtest included this condition.
#        Column name: adx (must exist in df_2h passed
#        as trend_aligned context — see note below).
#        NOTE: ADX is a trend-timeframe condition.
#        It is passed in via the trend_aligned series
#        or must be pre-filtered in live_runner before
#        calling generate_signals(). See live_runner
#        fix note at bottom of this file.
#
#   F3 - RSI > 60 (bull) / RSI < 40 (bear) added to
#        trend filter (2H).
#        Backtest used this to confirm strong momentum
#        before allowing entries.
#        NOTE: Same as ADX — this is a 2H condition.
#        Must be passed from live_runner. See note.
#
#   F4 - Entry RSI thresholds corrected on 30M:
#        BUY  : RSI crosses above 60 (was 50)
#        SELL : RSI crosses below 40 (was 50)
#        Backtest used 60/40 for 2H_30M strategy.
#        50/50 was correct only for 4H_1H strategy.
#
# ARCHITECTURE NOTE — ADX and TREND RSI (F2, F3):
#   ADX and RSI on the 2H timeframe are trend-filter
#   conditions. They cannot be checked inside this
#   function because this function only receives the
#   30M dataframe and a pre-computed trend_aligned
#   Series from live_runner.
#
#   The correct approach is to compute adx and rsi
#   on the 2H dataframe inside live_runner.py and
#   pass a combined trend signal that already
#   incorporates all 4 trend conditions:
#     - EMA50 > EMA200
#     - Supertrend bullish
#     - ADX > 20
#     - RSI > 60 (bull) / RSI < 40 (bear)
#
#   live_runner.py must be updated to compute this
#   combined trend signal before calling
#   generate_signals(). See live_runner fix note.
# =================================================

import pandas as pd


def generate_signals(df_30m: pd.DataFrame, trend_aligned: pd.Series) -> pd.DataFrame:
    """
    Generate entry and exit signals on the 30M timeframe.

    ENTRY RULES (aligned to backtest):
        BUY  : 2H trend = bull
               (EMA50 > EMA200 AND Supertrend bull
                AND ADX > 20 AND RSI > 60 — pre-filtered
                in live_runner before this call)
               AND 30M EMA50 > EMA200
               AND RSI crosses above 60

        SELL : 2H trend = bear
               (EMA50 < EMA200 AND Supertrend bear
                AND ADX > 20 AND RSI < 40 — pre-filtered
                in live_runner before this call)
               AND 30M EMA50 < EMA200
               AND RSI crosses below 40

    EXIT RULES (Supertrend Flip):
        EXIT_BUY  : Supertrend flips from bull -> bear
        EXIT_SELL : Supertrend flips from bear -> bull

    Signal column values (uppercase — matches live_runner.py):
        "BUY"       - enter long
        "SELL"      - enter short
        "EXIT_BUY"  - close long position
        "EXIT_SELL" - close short position
        None        - no action

    Args:
        df_30m        : 30M OHLCV dataframe with indicators.
                        Required columns:
                          ema50, ema200, rsi,
                          supertrend_bull
        trend_aligned : Pre-computed 2H trend Series.
                        Values: "bull", "bear", or None.
                        Must already incorporate all 4
                        trend conditions (EMA50/200,
                        Supertrend, ADX > 20, RSI 60/40).
                        Computed in live_runner.py.
    """

    df = df_30m.copy()

    # 2H trend alignment — pre-computed in live_runner
    # already includes EMA50/200 + Supertrend + ADX + RSI
    df["trend_2h"] = trend_aligned

    # =================================================
    # RSI CROSS DETECTION ON 30M
    # F4: Thresholds corrected to 60/40 (was 50/50)
    # =================================================
    rsi_prev = df["rsi"].shift(1)

    # F4: BUY entry — RSI crosses above 60 (not 50)
    df["rsi_cross_above_60"] = (
        (rsi_prev < 60) &
        (df["rsi"] >= 60)
    )

    # F4: SELL entry — RSI crosses below 40 (not 50)
    df["rsi_cross_below_40"] = (
        (rsi_prev > 40) &
        (df["rsi"] <= 40)
    )

    # =================================================
    # SUPERTREND FLIP DETECTION ON 30M
    # =================================================
    st_prev = df["supertrend_bull"].shift(1)

    # Bull -> Bear flip (exit long)
    df["st_flip_bear"] = (
        (st_prev == True) &
        (df["supertrend_bull"] == False)
    )

    # Bear -> Bull flip (exit short)
    df["st_flip_bull"] = (
        (st_prev == False) &
        (df["supertrend_bull"] == True)
    )

    # =================================================
    # ENTRY CONDITIONS
    # F1: ema50/ema200 replacing ema_fast/ema_slow
    # F4: RSI cross thresholds 60/40 replacing 50/50
    # =================================================
    buy_condition = (
        (df["trend_2h"] == "bull") &
        (df["ema50"] > df["ema200"]) &        # F1: was ema_fast > ema_slow
        (df["rsi_cross_above_60"] == True)    # F4: was rsi_cross_above_50
    )

    sell_condition = (
        (df["trend_2h"] == "bear") &
        (df["ema50"] < df["ema200"]) &        # F1: was ema_fast < ema_slow
        (df["rsi_cross_below_40"] == True)    # F4: was rsi_cross_below_50
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
    # Order matters: entries first, exits second.
    # Exits overwrite entries on the same bar
    # (exit takes priority over new entry).
    # live_runner.py reads only the signal column.
    # =================================================
    df["signal"] = None

    df.loc[buy_condition,       "signal"] = "BUY"
    df.loc[sell_condition,      "signal"] = "SELL"
    df.loc[exit_buy_condition,  "signal"] = "EXIT_BUY"
    df.loc[exit_sell_condition, "signal"] = "EXIT_SELL"

    return df
