# =====================================================
# backtest_engine.py
# Delta Exchange - Swing Backtest Engine
#
# SYSTEM LOGIC:
#   4H TREND FILTER:
#     BUY  - EMA50 > EMA200, Supertrend bullish, ADX > 20
#     SELL - EMA50 < EMA200, Supertrend bearish, ADX > 20
#
#   1H ENTRY TRIGGER:
#     BUY  - EMA50 > EMA200, close near EMA200 (within ATR*mult),
#             RSI crosses above 50
#     SELL - EMA50 < EMA200, close near EMA200 (within ATR*mult),
#             RSI crosses below 50
#
#   EXIT:
#     BUY  - Supertrend flips bearish  (on trigger TF)
#     SELL - Supertrend flips bullish  (on trigger TF)
#
# PREVIOUS FIXES RETAINED:
#   BUG1 - Trailing stop fires immediately when sl=0
#   BUG2 - Trigger TF wt/supertrend signals preserved after merge
#   BUG3 - ema_signal column missing = silent 5-vote system
#   BUG4 - RSI NaN becomes 0.0, adds spurious bull vote
#   BUG5 - No fee/slippage deducted from PnL
#   BUG6 - Imports inside function body
#   BUG7 - Double underscore in filename when label=""
# =====================================================

import sys
import os

# ── Path fix: allow imports from project root ─────────────────────
# This file lives at strategies/futures_4h_1h/backtest.py
# Root is two levels up
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import math
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ── Fixed imports after restructuring ────────────────────────────
# data_fetcher.py  →  core/data_fetcher.py
# indicators.py    →  core/indicators.py
# config.py        →  strategies/futures_4h_1h/config.py
from core.data_fetcher import fetch_candles_by_days
from strategies.futures_2h_30m import config
from core.indicators import add_all_indicators


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

# Results saved inside the strategy folder, not project root
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
EXIT_MODES  = ("opposite_signal", "atr_sl_tp", "trailing_stop")

# How close price must be to EMA200 to qualify as a
# pullback/rejection entry. Expressed as ATR multiplier.
# e.g. 1.0 means within 1x ATR of EMA200.
# Configurable via params["ema200_proximity_atr_mult"].
DEFAULT_EMA200_PROXIMITY_MULT = 1.0


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _safe_float(val, default: float = 0.0) -> float:
    """Convert pandas scalar / numpy type to plain Python float safely."""
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _safe_float_nan(val) -> float:
    """
    Returns float value, or NaN if missing/unconvertible.
    Used where 0.0 would produce a misleading result (e.g. RSI).
    """
    try:
        f = float(val)
        return f
    except (TypeError, ValueError):
        return float("nan")


def _timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _make_filename(prefix: str, symbol: str, label: str, ext: str) -> str:
    """Build a clean result filename with no double underscore."""
    label_part = f"_{label}" if label else ""
    ts = _timestamp_str()
    return os.path.join(RESULTS_DIR, f"{prefix}_{symbol}{label_part}_{ts}.{ext}")


def _supertrend_is_bullish(val) -> bool:
    """
    Normalise supertrend signal value to boolean bullish check.
    Accepts: 'bullish', 1, 1.0, True
    """
    if isinstance(val, str):
        return val.strip().lower() == "bullish"
    try:
        return float(val) > 0
    except (TypeError, ValueError):
        return False


def _supertrend_is_bearish(val) -> bool:
    """
    Normalise supertrend signal value to boolean bearish check.
    Accepts: 'bearish', -1, -1.0, False
    """
    if isinstance(val, str):
        return val.strip().lower() == "bearish"
    try:
        return float(val) < 0
    except (TypeError, ValueError):
        return False


# ─────────────────────────────────────────────
# TREND FILTER  (4H)
# ─────────────────────────────────────────────
def _trend_is_bullish(row: pd.Series, params: dict) -> bool:
    """
    4H trend filter - BUY side.
    Conditions (ALL must be true):
      1. EMA50 > EMA200
      2. Supertrend = bullish
      3. ADX > adx_min_threshold
      4. RSI > trend_rsi_min
    """
    adx_threshold = params.get("adx_min_threshold", 20)
    trend_rsi_min = params.get("trend_rsi_min", 55)

    ema50  = _safe_float_nan(row.get("ema50_trend"))
    ema200 = _safe_float_nan(row.get("ema200_trend"))
    adx    = _safe_float_nan(row.get("adx_trend"))
    rsi    = _safe_float_nan(row.get("rsi_trend"))
    st     = row.get("supertrend_signal_trend")

    if any(math.isnan(v) for v in [ema50, ema200, adx, rsi]):
        return False

    return (
        ema50 > ema200
        and _supertrend_is_bullish(st)
        and adx > adx_threshold
        and rsi > trend_rsi_min
    )


def _trend_is_bearish(row: pd.Series, params: dict) -> bool:
    """
    4H trend filter - SELL side.
    Conditions (ALL must be true):
      1. EMA50 < EMA200
      2. Supertrend = bearish
      3. ADX > adx_min_threshold
      4. RSI < (100 - trend_rsi_min)
    """
    adx_threshold = params.get("adx_min_threshold", 20)
    trend_rsi_min = params.get("trend_rsi_min", 55)

    ema50  = _safe_float_nan(row.get("ema50_trend"))
    ema200 = _safe_float_nan(row.get("ema200_trend"))
    adx    = _safe_float_nan(row.get("adx_trend"))
    rsi    = _safe_float_nan(row.get("rsi_trend"))
    st     = row.get("supertrend_signal_trend")

    if any(math.isnan(v) for v in [ema50, ema200, adx, rsi]):
        return False

    return (
        ema50 < ema200
        and _supertrend_is_bearish(st)
        and adx > adx_threshold
        and rsi < (100 - trend_rsi_min)
    )


# ─────────────────────────────────────────────
# ENTRY TRIGGER  (1H)
# ─────────────────────────────────────────────

def _rsi_crossed_above_50(prev_row: pd.Series, curr_row: pd.Series) -> bool:
    """
    RSI cross above 50: previous bar RSI < 50, current bar RSI >= 50.
    Returns False if either RSI value is NaN.
    """
    prev_rsi = _safe_float_nan(prev_row.get("rsi_trigger"))
    curr_rsi = _safe_float_nan(curr_row.get("rsi_trigger"))

    if math.isnan(prev_rsi) or math.isnan(curr_rsi):
        return False

    return prev_rsi < 60.0 and curr_rsi >= 60.0


def _rsi_crossed_below_50(prev_row: pd.Series, curr_row: pd.Series) -> bool:
    """
    RSI cross below 50: previous bar RSI > 50, current bar RSI <= 50.
    Returns False if either RSI value is NaN.
    """
    prev_rsi = _safe_float_nan(prev_row.get("rsi_trigger"))
    curr_rsi = _safe_float_nan(curr_row.get("rsi_trigger"))

    if math.isnan(prev_rsi) or math.isnan(curr_rsi):
        return False

    return prev_rsi > 40.0 and curr_rsi <= 40.0


def _trigger_buy(
    prev_row: pd.Series,
    curr_row: pd.Series,
    params: dict
) -> bool:
    """
    1H BUY entry trigger:
      1. EMA50 > EMA200
      2. RSI crosses above 50
    """
    ema50  = _safe_float_nan(curr_row.get("ema50_trigger"))
    ema200 = _safe_float_nan(curr_row.get("ema200_trigger"))

    if math.isnan(ema50) or math.isnan(ema200):
        return False

    return (
        ema50 > ema200
        and _rsi_crossed_above_50(prev_row, curr_row)
    )


def _trigger_sell(
    prev_row: pd.Series,
    curr_row: pd.Series,
    params: dict
) -> bool:
    """
    1H SELL entry trigger:
      1. EMA50 < EMA200
      2. RSI crosses below 50
    """
    ema50  = _safe_float_nan(curr_row.get("ema50_trigger"))
    ema200 = _safe_float_nan(curr_row.get("ema200_trigger"))

    if math.isnan(ema50) or math.isnan(ema200):
        return False

    return (
        ema50 < ema200
        and _rsi_crossed_below_50(prev_row, curr_row)
    )


# ─────────────────────────────────────────────
# EXIT LOGIC
# ─────────────────────────────────────────────
def _exit_signal(trade_side: str, curr_row: pd.Series) -> bool:
    """
    Supertrend flip exit on trigger TF.
      BUY  trade exits when supertrend flips bearish
      SELL trade exits when supertrend flips bullish

    Uses trigger TF supertrend_signal_trigger.
    """
    st = curr_row.get("supertrend_signal_trigger")

    if trade_side == "BUY":
        return _supertrend_is_bearish(st)
    else:
        return _supertrend_is_bullish(st)


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────
def _passes_filters(row: pd.Series, params: dict) -> bool:
    """
    Row-level pre-entry filters.
    All active filters must pass before a signal is evaluated.
    """
    # ── 1. Choppiness filter ──────────────────────────────────────
    if params.get("use_choppiness_filter", True):
        chop_threshold = params.get("choppiness_threshold", 61.8)
        choppiness = _safe_float(row.get("choppiness_trend", row.get("choppiness", 0)))
        is_choppy  = bool(row.get("is_choppy_trend", row.get("is_choppy", False)))
        if is_choppy or choppiness > chop_threshold:
            return False

    # ── 2. ATR volatility filter ──────────────────────────────────
    if params.get("use_volatility_filter", True):
        atr     = _safe_float(row.get("atr_trigger", row.get("atr", 0)))
        min_atr = params.get("min_atr_threshold", 0.0)
        if atr < min_atr:
            return False

    return True


# ─────────────────────────────────────────────
# TRADE OBJECT
# ─────────────────────────────────────────────
class Trade:
    """Represents a single completed or open trade."""

    __slots__ = (
        "symbol", "side", "entry_price", "entry_time",
        "exit_price", "exit_time", "exit_reason",
        "pnl_points", "pnl_pct", "pnl_pct_net",
        "lot_size", "sl_price", "tp_price", "trailing_sl",
        "system", "trend_tf", "trigger_tf",
        "fee_pct_per_side"
    )

    def __init__(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        entry_time,
        lot_size: float,
        sl_price: float         = 0.0,
        tp_price: float         = 0.0,
        system: str             = "",
        trend_tf: str           = "",
        trigger_tf: str         = "",
        fee_pct_per_side: float = 0.0
    ):
        self.symbol           = symbol
        self.side             = side
        self.entry_price      = entry_price
        self.entry_time       = entry_time
        self.lot_size         = lot_size
        self.sl_price         = sl_price
        self.tp_price         = tp_price
        self.trailing_sl      = sl_price
        self.system           = system
        self.trend_tf         = trend_tf
        self.trigger_tf       = trigger_tf
        self.fee_pct_per_side = fee_pct_per_side

        self.exit_price   = None
        self.exit_time    = None
        self.exit_reason  = None
        self.pnl_points   = None
        self.pnl_pct      = None
        self.pnl_pct_net  = None

    def close(self, exit_price: float, exit_time, reason: str) -> None:
        self.exit_price  = exit_price
        self.exit_time   = exit_time
        self.exit_reason = reason

        if self.side == "BUY":
            self.pnl_points = exit_price - self.entry_price
        else:
            self.pnl_points = self.entry_price - exit_price

        self.pnl_pct     = (self.pnl_points / self.entry_price) * 100
        round_trip_fee   = self.fee_pct_per_side * 2
        self.pnl_pct_net = self.pnl_pct - round_trip_fee

    def is_open(self) -> bool:
        return self.exit_price is None

    def to_dict(self) -> dict:
        return {
            "symbol"      : self.symbol,
            "side"        : self.side,
            "system"      : self.system,
            "trend_tf"    : self.trend_tf,
            "trigger_tf"  : self.trigger_tf,
            "entry_time"  : self.entry_time,
            "entry_price" : round(self.entry_price, 4),
            "exit_time"   : self.exit_time,
            "exit_price"  : round(self.exit_price,  4) if self.exit_price  is not None else None,
            "exit_reason" : self.exit_reason,
            "pnl_points"  : round(self.pnl_points,  4) if self.pnl_points  is not None else None,
            "pnl_pct"     : round(self.pnl_pct,     4) if self.pnl_pct     is not None else None,
            "pnl_pct_net" : round(self.pnl_pct_net, 4) if self.pnl_pct_net is not None else None,
            "lot_size"    : self.lot_size,
            "fee_pct_rt"  : round(self.fee_pct_per_side * 2, 4),
        }


# ─────────────────────────────────────────────
# EXIT HANDLERS  (ATR SL/TP + Trailing)
# ─────────────────────────────────────────────
def _check_atr_sl_tp(trade: Trade, row: pd.Series) -> tuple:
    """
    Check if current candle hits SL or TP.
    Uses candle high/low for realistic fill simulation.
    Returns (should_close, exit_price, reason).
    """
    high  = _safe_float(row.get("high",  trade.entry_price))
    low   = _safe_float(row.get("low",   trade.entry_price))
    close = _safe_float(row.get("close", trade.entry_price))

    if trade.side == "BUY":
        if trade.sl_price > 0 and low  <= trade.sl_price:
            return True, trade.sl_price, "sl_hit"
        if trade.tp_price > 0 and high >= trade.tp_price:
            return True, trade.tp_price, "tp_hit"
    else:
        if trade.sl_price > 0 and high >= trade.sl_price:
            return True, trade.sl_price, "sl_hit"
        if trade.tp_price > 0 and low  <= trade.tp_price:
            return True, trade.tp_price, "tp_hit"

    return False, close, "open"


def _update_trailing_stop(
    trade: Trade,
    row: pd.Series,
    params: dict
) -> None:
    """
    Ratchet trailing stop using ATR multiplier.
    Only moves stop in the profitable direction.
    """
    atr        = _safe_float(row.get("atr_trigger", row.get("atr", 0)))
    multiplier = params.get("trailing_atr_multiplier", 2.0)
    trail_dist = atr * multiplier

    if trail_dist == 0:
        return

    high = _safe_float(row.get("high", trade.entry_price))
    low  = _safe_float(row.get("low",  trade.entry_price))

    if trade.side == "BUY":
        new_sl = high - trail_dist
        if new_sl > trade.trailing_sl:
            trade.trailing_sl = new_sl
    else:
        new_sl = low + trail_dist
        if trade.trailing_sl == 0.0 or new_sl < trade.trailing_sl:
            trade.trailing_sl = new_sl


def _check_trailing_stop(trade: Trade, row: pd.Series) -> tuple:
    """
    Check if trailing stop is hit.
    Guard against trailing_sl == 0.0 to prevent immediate exit.
    Returns (should_close, exit_price, reason).
    """
    if trade.trailing_sl == 0.0:
        return False, _safe_float(row.get("close", trade.entry_price)), "open"

    low   = _safe_float(row.get("low",   trade.entry_price))
    high  = _safe_float(row.get("high",  trade.entry_price))
    close = _safe_float(row.get("close", trade.entry_price))

    if trade.side == "BUY":
        if low <= trade.trailing_sl:
            return True, trade.trailing_sl, "trailing_sl_hit"
    else:
        if high >= trade.trailing_sl:
            return True, trade.trailing_sl, "trailing_sl_hit"

    return False, close, "open"


# ─────────────────────────────────────────────
# MERGE HELPER
# ─────────────────────────────────────────────
def _build_merged_df(
    df_trend: pd.DataFrame,
    df_trigger: pd.DataFrame
) -> pd.DataFrame:
    """
    Merge trend TF indicators onto trigger TF candles using
    merge_asof (backward fill - zero lookahead).

    After merge, ALL columns are suffixed _trend or _trigger.
    Signal functions read explicitly suffixed columns so there
    is never ambiguity about which timeframe a value came from.

    Columns produced (examples):
      ema50_trend, ema200_trend, adx_trend, supertrend_signal_trend
      ema50_trigger, ema200_trigger, rsi_trigger, atr_trigger
      supertrend_signal_trigger, choppiness_trend, is_choppy_trend
    """
    df_trend["datetime"]   = pd.to_datetime(df_trend["datetime"])
    df_trigger["datetime"] = pd.to_datetime(df_trigger["datetime"])

    trend_indicator_cols = [
        "ema50",
        "ema200",
        "adx",
        "rsi",
        "supertrend_signal",
        "choppiness",
        "is_choppy",
        "atr",
    ]
    trend_cols = ["datetime"] + [
        c for c in trend_indicator_cols if c in df_trend.columns
    ]

    df_merged = pd.merge_asof(
        df_trigger.sort_values("datetime"),
        df_trend[trend_cols].sort_values("datetime"),
        on        = "datetime",
        direction = "backward",
        suffixes  = ("_trigger", "_trend")
    ).copy()

    return df_merged


# ─────────────────────────────────────────────
# REQUIRED COLUMN VALIDATOR
# ─────────────────────────────────────────────
def _check_required_columns(df: pd.DataFrame, symbol: str) -> bool:
    """
    Verify all columns the signal logic depends on are present
    after the merge. Prints a clear diagnostic if any are missing.
    Returns True if all present, False otherwise.
    """
    required = [
        # Trend TF
        "ema50_trend",
        "ema200_trend",
        "adx_trend",
        "supertrend_signal_trend",
        # Trigger TF
        "ema50_trigger",
        "ema200_trigger",
        "rsi_trigger",
        "atr_trigger",
        "supertrend_signal_trigger",
        # OHLCV
        "open", "high", "low", "close", "datetime",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        print(
            f"\n  [ERROR] {symbol}: Missing columns after merge.\n"
            f"  These columns are required but not found:\n"
            f"    {missing}\n"
            f"  Check that indicators.py produces these column names:\n"
            f"    ema50, ema200, adx, supertrend_signal, rsi, atr\n"
            f"  Available columns: {sorted(df.columns.tolist())}"
        )
        return False

    return True


# ─────────────────────────────────────────────
# CORE BACKTEST LOOP
# ─────────────────────────────────────────────
def run_backtest(
    symbol: str,
    df_trend: pd.DataFrame,
    df_trigger: pd.DataFrame,
    params: dict
) -> list:
    """
    Row-by-row backtest implementing the swing system:

      4H trend filter  ->  EMA50/200 + Supertrend + ADX
      1H entry trigger ->  EMA50/200 alignment + near EMA200 + RSI cross 50
      Exit             ->  Supertrend flip on 1H

    Args:
        symbol     : e.g. 'BTCUSD'
        df_trend   : OHLCV DataFrame for trend TF (e.g. 4h)
        df_trigger : OHLCV DataFrame for trigger TF (e.g. 1h)
        params     : Config dict

    Returns:
        List of Trade objects
    """
    exit_mode = params.get("exit_mode", "opposite_signal")
    if exit_mode not in EXIT_MODES:
        raise ValueError(
            f"Invalid exit_mode '{exit_mode}'. "
            f"Choose from: {EXIT_MODES}"
        )

    # ── Add indicators ────────────────────────────────────────────
    df_trend   = add_all_indicators(df_trend.copy(),   params)
    df_trigger = add_all_indicators(df_trigger.copy(), params)

    # ── Merge ─────────────────────────────────────────────────────
    df_merged = _build_merged_df(df_trend, df_trigger)

    # ── Validate columns ──────────────────────────────────────────
    if not _check_required_columns(df_merged, symbol):
        return []

    # ── Drop warmup NaN rows ──────────────────────────────────────
    warmup_cols = [
        "ema50_trend", "ema200_trend",
        "ema50_trigger", "ema200_trigger",
        "rsi_trigger", "atr_trigger",
        "adx_trend",
    ]
    warmup_cols_present = [c for c in warmup_cols if c in df_merged.columns]
    df_merged = df_merged.dropna(
        subset=warmup_cols_present
    ).reset_index(drop=True)

    if df_merged.empty:
        print(
            f"  [BACKTEST] {symbol}: All rows dropped during indicator warmup.\n"
            f"  Increase backtest_days in config (recommend >= 365 for EMA200)."
        )
        return []

    print(
        f"  [BACKTEST] {symbol}: {len(df_merged)} usable rows after warmup drop."
    )

    # ── Parameters ───────────────────────────────────────────────
    lot_size         = params.get("lot_size",           1)
    atr_sl_mult      = params.get("atr_sl_multiplier",  1.5)
    atr_tp_mult      = params.get("atr_tp_multiplier",  3.0)
    trend_tf         = params.get("trend_tf",           "4h")
    trigger_tf       = params.get("trigger_tf",         "1h")
    fee_pct_per_side = params.get("taker_fee_pct",      0.05)

    # ── State ─────────────────────────────────────────────────────
    trades     = []
    open_trade = None

    # ── Row-by-row replay ─────────────────────────────────────────
    for idx in range(1, len(df_merged)):

        curr_row  = df_merged.iloc[idx]
        prev_row  = df_merged.iloc[idx - 1]

        close     = _safe_float(curr_row.get("close"))
        atr       = _safe_float(curr_row.get("atr_trigger", 0))
        timestamp = curr_row["datetime"]

        if close == 0:
            continue

        # ── Manage open trade ─────────────────────────────────────
        if open_trade is not None:

            if exit_mode == "opposite_signal":
                if _exit_signal(open_trade.side, curr_row):
                    open_trade.close(close, timestamp, "supertrend_flip")
                    trades.append(open_trade)
                    open_trade = None

            elif exit_mode == "atr_sl_tp":
                should_close, exit_px, reason = _check_atr_sl_tp(
                    open_trade, curr_row
                )
                if should_close:
                    open_trade.close(exit_px, timestamp, reason)
                    trades.append(open_trade)
                    open_trade = None

            elif exit_mode == "trailing_stop":
                _update_trailing_stop(open_trade, curr_row, params)
                should_close, exit_px, reason = _check_trailing_stop(
                    open_trade, curr_row
                )
                if should_close:
                    open_trade.close(exit_px, timestamp, reason)
                    trades.append(open_trade)
                    open_trade = None

        # ── Pre-entry filters ─────────────────────────────────────
        if not _passes_filters(curr_row, params):
            continue

        # ── 4H Trend filter ───────────────────────────────────────
        bull_trend = _trend_is_bullish(curr_row, params)
        bear_trend = _trend_is_bearish(curr_row, params)

        if not bull_trend and not bear_trend:
            continue

        # ── 1H Entry trigger ──────────────────────────────────────
        signal = "NONE"

        if bull_trend and _trigger_buy(prev_row, curr_row, params):
            signal = "BUY"
        elif bear_trend and _trigger_sell(prev_row, curr_row, params):
            signal = "SELL"

        if signal == "NONE":
            continue

        # ── Skip if already in same direction ─────────────────────
        if open_trade is not None:
            if (signal == "BUY"  and open_trade.side == "BUY") or \
               (signal == "SELL" and open_trade.side == "SELL"):
                continue
            open_trade.close(close, timestamp, "opposite_signal")
            trades.append(open_trade)
            open_trade = None

        # ── Compute SL / TP ───────────────────────────────────────
        if exit_mode in ("atr_sl_tp", "trailing_stop") and atr > 0:
            if signal == "BUY":
                sl = close - atr * atr_sl_mult
                tp = close + atr * atr_tp_mult
            else:
                sl = close + atr * atr_sl_mult
                tp = close - atr * atr_tp_mult
        else:
            sl = 0.0
            tp = 0.0

        # ── Open trade ────────────────────────────────────────────
        open_trade = Trade(
            symbol           = symbol,
            side             = signal,
            entry_price      = close,
            entry_time       = timestamp,
            lot_size         = lot_size,
            sl_price         = sl,
            tp_price         = tp,
            system           = "swing_4h_1h",
            trend_tf         = trend_tf,
            trigger_tf       = trigger_tf,
            fee_pct_per_side = fee_pct_per_side
        )

    # ── Force-close at end of data ────────────────────────────────
    if open_trade is not None and open_trade.is_open():
        last_row   = df_merged.iloc[-1]
        last_close = _safe_float(last_row.get("close", 0))
        last_time  = last_row["datetime"]
        open_trade.close(last_close, last_time, "end_of_data")
        trades.append(open_trade)

    return trades


# ─────────────────────────────────────────────
# METRICS CALCULATOR
# ─────────────────────────────────────────────
def calculate_metrics(trades: list, symbol: str) -> dict:
    """
    Compute all backtest performance metrics.
    Primary metric is pnl_pct_net (after round-trip fees).
    """
    closed = [t for t in trades if not t.is_open()]

    empty = {
        "symbol"            : symbol,
        "total_trades"      : 0,
        "win_rate_pct"      : 0.0,
        "profit_factor"     : 0.0,
        "total_pnl_pct"     : 0.0,
        "total_pnl_pct_net" : 0.0,
        "max_drawdown_pct"  : 0.0,
        "avg_win_pct"       : 0.0,
        "avg_loss_pct"      : 0.0,
        "best_trade_pct"    : 0.0,
        "worst_trade_pct"   : 0.0,
        "avg_trade_pct"     : 0.0,
        "total_trades_buy"  : 0,
        "total_trades_sell" : 0,
        "win_streak_max"    : 0,
        "loss_streak_max"   : 0,
    }

    if not closed:
        return empty

    pnl_list     = [t.pnl_pct_net for t in closed]
    pnl_list_raw = [t.pnl_pct     for t in closed]

    wins   = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p <= 0]

    gross_profit = sum(wins)        if wins   else 0.0
    gross_loss   = abs(sum(losses)) if losses else 0.0

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else float("inf") if gross_profit > 0 else 0.0
    )

    equity = list(np.cumsum(pnl_list))
    peak   = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_dd:
            max_dd = dd

    win_streak = loss_streak = cur_win = cur_loss = 0
    for p in pnl_list:
        if p > 0:
            cur_win  += 1
            cur_loss  = 0
        else:
            cur_loss += 1
            cur_win   = 0
        win_streak  = max(win_streak,  cur_win)
        loss_streak = max(loss_streak, cur_loss)

    buy_trades  = sum(1 for t in closed if t.side == "BUY")
    sell_trades = sum(1 for t in closed if t.side == "SELL")

    return {
        "symbol"            : symbol,
        "total_trades"      : len(closed),
        "win_rate_pct"      : round(len(wins) / len(closed) * 100, 2),
        "profit_factor"     : round(profit_factor, 3),
        "total_pnl_pct"     : round(sum(pnl_list_raw), 4),
        "total_pnl_pct_net" : round(sum(pnl_list),     4),
        "max_drawdown_pct"  : round(max_dd, 4),
        "avg_win_pct"       : round(sum(wins)   / len(wins)   if wins   else 0, 4),
        "avg_loss_pct"      : round(sum(losses) / len(losses) if losses else 0, 4),
        "best_trade_pct"    : round(max(pnl_list), 4),
        "worst_trade_pct"   : round(min(pnl_list), 4),
        "avg_trade_pct"     : round(sum(pnl_list) / len(pnl_list), 4),
        "total_trades_buy"  : buy_trades,
        "total_trades_sell" : sell_trades,
        "win_streak_max"    : win_streak,
        "loss_streak_max"   : loss_streak,
    }


# ─────────────────────────────────────────────
# EQUITY CURVE CHART
# ─────────────────────────────────────────────
def save_equity_curve(
    trades: list,
    symbol: str,
    label: str = ""
) -> str:
    """Save equity curve PNG to strategy results folder. Returns file path."""
    _ensure_results_dir()

    closed = [t for t in trades if not t.is_open()]
    if not closed:
        return ""

    times      = [t.exit_time   for t in closed]
    pnl_net    = [t.pnl_pct_net for t in closed]
    equity_net = list(np.cumsum(pnl_net))

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    label_str = f"  |  {label}" if label else ""
    fig.suptitle(
        f"Equity Curve  |  {symbol}{label_str}",
        fontsize=14, fontweight="bold"
    )

    ax1 = axes[0]
    ax1.plot(times, equity_net, color="#2196F3", linewidth=1.5,
             label="Net Equity (% after fees)")
    ax1.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax1.fill_between(
        times, equity_net, 0,
        where=[e >= 0 for e in equity_net],
        alpha=0.15, color="#4CAF50", label="Profit zone"
    )
    ax1.fill_between(
        times, equity_net, 0,
        where=[e < 0 for e in equity_net],
        alpha=0.15, color="#F44336", label="Loss zone"
    )
    ax1.set_ylabel("Cumulative PnL % (net)")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2 = axes[1]
    colors = ["#4CAF50" if p > 0 else "#F44336" for p in pnl_net]
    ax2.bar(times, pnl_net, color=colors, width=0.6, alpha=0.8)
    ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax2.set_ylabel("Per-Trade PnL % (net)")
    ax2.set_xlabel("Exit Time")
    ax2.grid(True, alpha=0.3)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()

    filename = _make_filename("equity", symbol, label, "png")
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return filename


# ─────────────────────────────────────────────
# CSV EXPORT
# ─────────────────────────────────────────────
def save_trades_csv(trades: list, symbol: str, label: str = "") -> str:
    """Save all closed trades to CSV. Returns file path."""
    _ensure_results_dir()

    closed = [t for t in trades if not t.is_open()]
    if not closed:
        return ""

    df = pd.DataFrame([t.to_dict() for t in closed])
    filename = _make_filename("trades", symbol, label, "csv")
    df.to_csv(filename, index=False)
    return filename


def save_metrics_csv(metrics_list: list, label: str = "") -> str:
    """Save summary metrics for all symbols to CSV. Returns file path."""
    _ensure_results_dir()

    if not metrics_list:
        return ""

    df = pd.DataFrame(metrics_list)
    label_part = f"_{label}" if label else ""
    ts       = _timestamp_str()
    filename = os.path.join(RESULTS_DIR, f"summary{label_part}_{ts}.csv")
    df.to_csv(filename, index=False)
    return filename


# ─────────────────────────────────────────────
# TERMINAL REPORT
# ─────────────────────────────────────────────
def print_backtest_report(metrics_list: list) -> None:
    """Print formatted summary table to terminal."""
    if not metrics_list:
        print("  [BACKTEST] No results to display.")
        return

    print(
        f"\n{'='*100}\n"
        f"  BACKTEST REPORT  |  "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'='*100}"
    )

    col_fmt = (
        "{:<10} {:>7} {:>8} {:>8} {:>12} {:>12} {:>12} {:>10} {:>10}"
    )
    print(col_fmt.format(
        "SYMBOL", "TRADES", "WIN%", "PF",
        "GROSS PNL%", "NET PNL%", "MAX DD%",
        "AVG WIN%", "AVG LOSS%"
    ))
    print("-" * 100)

    for m in metrics_list:
        print(col_fmt.format(
            m["symbol"],
            m["total_trades"],
            f"{m['win_rate_pct']:.1f}%",
            f"{m['profit_factor']:.2f}",
            f"{m['total_pnl_pct']:.2f}%",
            f"{m['total_pnl_pct_net']:.2f}%",
            f"{m['max_drawdown_pct']:.2f}%",
            f"{m['avg_win_pct']:.2f}%",
            f"{m['avg_loss_pct']:.2f}%",
        ))

    print("=" * 100)

    valid = [m for m in metrics_list if m["total_trades"] > 0]
    if valid:
        best = max(valid, key=lambda x: x["profit_factor"])
        print(
            f"\n  Best performer : {best['symbol']}  "
            f"(PF={best['profit_factor']:.2f}, "
            f"Win={best['win_rate_pct']:.1f}%, "
            f"Net PnL={best['total_pnl_pct_net']:.2f}%, "
            f"Trades={best['total_trades']})"
        )
    print()


# ─────────────────────────────────────────────
# MULTI-SYMBOL RUNNER
# ─────────────────────────────────────────────
def run_backtest_all_symbols(
    symbols: list,
    params_map: dict,
    label: str = ""
) -> list:

    all_metrics = []

    empty_metrics = {
        "win_rate_pct"      : 0,
        "profit_factor"     : 0,
        "total_pnl_pct"     : 0,
        "total_pnl_pct_net" : 0,
        "max_drawdown_pct"  : 0,
        "avg_win_pct"       : 0,
        "avg_loss_pct"      : 0,
        "best_trade_pct"    : 0,
        "worst_trade_pct"   : 0,
        "avg_trade_pct"     : 0,
        "total_trades_buy"  : 0,
        "total_trades_sell" : 0,
        "win_streak_max"    : 0,
        "loss_streak_max"   : 0,
    }

    for symbol in symbols:

        params     = params_map[symbol]
        trend_tf   = params.get("trend_tf",   "4h")
        trigger_tf = params.get("trigger_tf", "1h")
        days       = params.get(
            "backtest_days",
            getattr(config, "BACKTEST_DAYS", 365)
        )

        print(f"\n  [BACKTEST] Processing {symbol} ...")

        try:
            df_trend = fetch_candles_by_days(symbol, trend_tf,   days=days)
            df_trigger = fetch_candles_by_days(symbol, trigger_tf, days=days)

            if df_trend.empty or df_trigger.empty:
                print(f"  SKIP {symbol} (no data)")
                all_metrics.append(
                    {"symbol": symbol, "total_trades": 0, **empty_metrics}
                )
                continue

            trades  = run_backtest(symbol, df_trend, df_trigger, params)
            metrics = calculate_metrics(trades, symbol)
            all_metrics.append(metrics)

            trades_path = save_trades_csv(trades, symbol, label)
            chart_path  = save_equity_curve(trades, symbol, label)

            print(
                f"  OK | trades={metrics['total_trades']} "
                f"win={metrics['win_rate_pct']:.1f}% "
                f"PF={metrics['profit_factor']:.2f} "
                f"net={metrics['total_pnl_pct_net']:.2f}%"
            )

            if trades_path:
                print(f"     trades CSV : {trades_path}")
            if chart_path:
                print(f"     chart PNG  : {chart_path}")

        except Exception as e:
            print(f"  ERROR {symbol}: {e}")
            all_metrics.append(
                {"symbol": symbol, "total_trades": 0, **empty_metrics}
            )

    summary_path = save_metrics_csv(all_metrics, label)
    print_backtest_report(all_metrics)

    if summary_path:
        print(f"\n  [BACKTEST] Summary CSV : {summary_path}")

    return all_metrics
