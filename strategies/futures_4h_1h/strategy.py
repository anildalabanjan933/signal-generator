# =================================================
# strategy.py - futures_4h_1h
# 1H Entry Signal Generator
# Trend direction from 4H candles
# Entry signals from 1H candles
#
# FIXES APPLIED:
#   F1 - ema_fast/ema_slow replaced with ema50/ema200
#        on both trend check and entry condition.
#        ema_fast/ema_slow were EMA9/EMA21 — short-term
#        noise EMAs. Backtest used EMA50/EMA200.
#        Column names ema50 and ema200 must be present
#        in the dataframe passed from live_runner.py.
#
#   F2 - ADX > 20 added to trend filter (4H).
#        Filters out ranging/sideways markets.
#        Backtest included this condition.
#        NOTE: ADX is a 4H trend-timeframe condition.
#        Must be pre-filtered in live_runner before
#        calling generate_signals(). See note below.
#
#   F3 - RSI > 60 (bull) / RSI < 40 (bear) added to
#        trend filter (4H).
#        Backtest used this to confirm strong momentum.
#        NOTE: Same as ADX — this is a 4H condition.
#        Must be passed from live_runner. See note.
#
#   F4 - Entry RSI threshold stays at 50/50 for this
#        strategy. 4H_1H backtest used RSI cross
#        above/below 50 on 1H. No change needed here.
#
#   F5 - Signal values corrected to uppercase.
#        Was: "buy", "sell", "exit_buy", "exit_sell"
#        Now: "BUY", "SELL", "EXIT_BUY", "EXIT_SELL"
#        live_runner.py checks uppercase. Mismatch
#        caused zero signal executions.
#
#   F6 - Separate exit_signal column removed.
#        exit_buy and exit_sell now written into the
#        single signal column directly.
#        live_runner.py reads only signal column.
#        Separate exit_signal column caused KeyError
#        in live_runner after previous session fix.
#
# ARCHITECTURE NOTE — ADX and TREND RSI (F2, F3):
#   ADX and RSI on the 4H timeframe are trend-filter
#   conditions. They cannot be checked inside this
#   function because this function only receives the
#   1H dataframe and a pre-computed trend_aligned
#   Series from live_runner.
#
#   The correct approach is to compute adx and rsi
#   on the 4H dataframe inside live_runner.py and
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


def generate_signals(df_1h: pd.DataFrame, trend_aligned: pd.Series) -> pd.DataFrame:
    """
    Generate entry and exit signals on the 1H timeframe.

    ENTRY RULES (aligned to backtest):
        BUY  : 4H trend = bull
               (EMA50 > EMA200 AND Supertrend bull
                AND ADX > 20 AND RSI > 60 — pre-filtered
                in live_runner before this call)
               AND 1H EMA50 > EMA200
               AND RSI crosses above 50

        SELL : 4H trend = bear
               (EMA50 < EMA200 AND Supertrend bear
                AND ADX > 20 AND RSI < 40 — pre-filtered
                in live_runner before this call)
               AND 1H EMA50 < EMA200
               AND RSI crosses below 50

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
        df_1h         : 1H OHLCV dataframe with indicators.
                        Required columns:
                          ema50, ema200, rsi,
                          supertrend_bull
        trend_aligned : Pre-computed 4H trend Series.
                        Values: "bull", "bear", or None.
                        Must already incorporate all 4
                        trend conditions (EMA50/200,
                        Supertrend, ADX > 20, RSI 60/40).
                        Computed in live_runner.py.
    """

    df = df_1h.copy()

    # 4H trend alignment — pre-computed in live_runner
    # already includes EMA50/200 + Supertrend + ADX + RSI
    df["trend_4h"] = trend_aligned

    # =================================================
    # RSI CROSS DETECTION ON 1H
    # F4: Threshold stays at 50/50 for 4H_1H strategy
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
    # SUPERTREND FLIP DETECTION ON 1H
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
    # =================================================
    buy_condition = (
        (df["trend_4h"] == "bull") &
        (df["ema50"] > df["ema200"]) &        # F1: was ema_fast > ema_slow
        (df["rsi_cross_above_50"] == True)
    )

    sell_condition = (
        (df["trend_4h"] == "bear") &
        (df["ema50"] < df["ema200"]) &        # F1: was ema_fast < ema_slow
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
    # F5: All values uppercase
    # F6: No separate exit_signal column
    # Order: entries first, exits second.
    # Exits overwrite entries on the same bar.
    # live_runner.py reads only the signal column.
    # =================================================
    df["signal"] = None

    df.loc[buy_condition,       "signal"] = "BUY"
    df.loc[sell_condition,      "signal"] = "SELL"
    df.loc[exit_buy_condition,  "signal"] = "EXIT_BUY"
    df.loc[exit_sell_condition, "signal"] = "EXIT_SELL"

    return df
