# ============================================================
# live_runner.py  -  futures_2h_30m strategy
# ============================================================
# Timeframe structure:
#   2H candles  ->  trend direction
#   30M candles ->  entry signal
#
# FIXES APPLIED (this session):
#   F6 - apply_indicators() now computes ema50 and ema200
#        instead of ema_fast (EMA9) and ema_slow (EMA21).
#        strategy.py expects ema50/ema200 column names.
#        ema_fast/ema_slow caused KeyError in strategy.
#
#   F7 - apply_indicators() now computes ADX (14-period).
#        ADX was not computed at all previously.
#        Trend filter requires ADX > 20 to confirm
#        directional momentum. Without ADX the bot was
#        taking signals in ranging/sideways markets.
#
#   F8 - get_2h_trend() now uses all 4 backtest conditions:
#        BULL: ema50 > ema200 AND supertrend_bull AND
#              adx > 20 AND rsi > 60
#        BEAR: ema50 < ema200 AND NOT supertrend_bull AND
#              adx > 20 AND rsi < 40
#        NONE: conditions not met — no trade allowed
#        Previously only ema_fast > ema_slow was checked.
#        Supertrend, ADX, and RSI were all ignored.
#
#   F9 - trend_aligned now carries "bull"/"bear"/None.
#        generate_signals() in strategy.py already handles
#        None as no-trade. No change needed in strategy.
#
# FIXES FROM PREVIOUS SESSION (retained):
#   F1 - Signal comparisons corrected to uppercase.
#   F2 - exit_signal separate column removed.
#   F3 - ffill() replaces deprecated fillna(method="ffill").
#   F4 - guard and allocator at module level.
#   F5 - run_once() added for scanner.py coordinator.
# ============================================================

import sys
import os
import time
import requests
import pandas as pd
from datetime import datetime

# ----------------------------------------
# PATH FIX
# ----------------------------------------
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(__file__))

# ----------------------------------------
# STRATEGY
# ----------------------------------------
from strategy import generate_signals

# ----------------------------------------
# EXECUTION + RISK
# ----------------------------------------
from execution.demo_executor import execute_signal
from risk.daily_guard import DailyGuard
from risk.trade_allocator import TradeAllocator
from risk.position_sizer import calculate_position_size

# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://api.india.delta.exchange"

SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "BNBUSD",
    "DOGEUSD",
]

RESOLUTION_TREND       = "2h"
RESOLUTION_ENTRY       = "30m"
CANDLE_LIMIT           = 100
CHECK_INTERVAL_SECONDS = 1800

RESOLUTION_SECONDS = {
    "1m"  : 60,
    "3m"  : 180,
    "5m"  : 300,
    "15m" : 900,
    "30m" : 1800,
    "1h"  : 3600,
    "2h"  : 7200,
    "4h"  : 14400,
    "6h"  : 21600,
    "1d"  : 86400,
}

last_signal_map = {}

# ============================================================
# F4: MODULE-LEVEL RISK INSTANCES
# ============================================================
guard     = DailyGuard()
allocator = TradeAllocator()

# ============================================================
# LIVE CANDLE FETCHER
# ============================================================

def fetch_candles(
    symbol    : str,
    resolution: str = "30m",
    limit     : int = 100
) -> pd.DataFrame:

    end_ts          = int(time.time())
    resolution_secs = RESOLUTION_SECONDS.get(resolution, 1800)
    start_ts        = end_ts - (limit * resolution_secs)

    url    = f"{BASE_URL}/v2/history/candles"
    params = {
        "symbol"    : symbol,
        "resolution": resolution,
        "start"     : start_ts,
        "end"       : end_ts,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            raise ValueError(f"API returned success=false for {symbol}")

        candles = data.get("result", [])

        if not candles:
            raise ValueError(f"No candle data for {symbol}")

        df = pd.DataFrame(candles)
        df.rename(columns={"time": "timestamp"}, inplace=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        df["timestamp"] = pd.to_datetime(
            df["timestamp"], unit="s", utc=True
        )

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        return df

    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Network error for {symbol}: {e}")

    except Exception as e:
        raise RuntimeError(f"Failed fetching candles for {symbol}: {e}")

# ============================================================
# INDICATORS
# F6: ema_fast/ema_slow replaced with ema50/ema200.
# F7: ADX (14-period) added. Required for trend filter.
#
# This function is called on BOTH the 30M entry dataframe
# and the 2H trend dataframe. All columns are computed
# on both so the trend builder can access rsi, adx,
# ema50, ema200, supertrend_bull on the 2H dataframe.
# ============================================================

def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:

    # ---- RSI (14-period) ----
    delta_close = df["close"].diff()
    gain        = delta_close.clip(lower=0)
    loss        = -delta_close.clip(upper=0)
    avg_gain    = gain.ewm(com=13, min_periods=14).mean()
    avg_loss    = loss.ewm(com=13, min_periods=14).mean()
    rs          = avg_gain / avg_loss
    df["rsi"]   = 100 - (100 / (1 + rs))

    # ---- EMA50 and EMA200 ----
    # F6: Replaces ema_fast (EMA9) and ema_slow (EMA21).
    # Backtest used EMA50/EMA200 for trend and entry.
    df["ema50"]  = df["close"].ewm(span=50,  adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    # ---- ADX (14-period) ----
    # F7: ADX was missing entirely. Required for trend filter.
    # Standard Wilder ADX calculation.
    high        = df["high"]
    low         = df["low"]
    close       = df["close"]

    plus_dm     = high.diff()
    minus_dm    = low.diff().abs()

    plus_dm     = plus_dm.where(
        (plus_dm > minus_dm) & (plus_dm > 0), 0.0
    )
    minus_dm    = minus_dm.where(
        (minus_dm > plus_dm.abs()) & (minus_dm > 0), 0.0
    )

    high_low    = high - low
    high_close  = (high - close.shift()).abs()
    low_close   = (low  - close.shift()).abs()

    tr          = pd.concat(
        [high_low, high_close, low_close], axis=1
    ).max(axis=1)

    atr14       = tr.ewm(span=14, adjust=False).mean()
    plus_di     = 100 * (plus_dm.ewm(span=14, adjust=False).mean()  / atr14)
    minus_di    = 100 * (minus_dm.ewm(span=14, adjust=False).mean() / atr14)

    dx          = (
        (plus_di - minus_di).abs() /
        (plus_di + minus_di).abs()
    ) * 100

    df["adx"]   = dx.ewm(span=14, adjust=False).mean()

    # ---- Supertrend (ATR 10, multiplier 3.0) ----
    atr_period     = 10
    atr_multiplier = 3.0

    hl2        = (df["high"] + df["low"]) / 2
    atr_st     = tr.ewm(span=atr_period, adjust=False).mean()
    upper_band = hl2 + (atr_multiplier * atr_st)
    lower_band = hl2 - (atr_multiplier * atr_st)

    supertrend = [True] * len(df)

    for i in range(1, len(df)):
        if df["close"].iloc[i] > upper_band.iloc[i]:
            supertrend[i] = True
        elif df["close"].iloc[i] < lower_band.iloc[i]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i - 1]

    df["supertrend_bull"] = pd.array(supertrend, dtype="boolean")

    return df

# ============================================================
# 2H TREND BUILDER
# F8: All 4 backtest trend conditions now applied.
#
# BULL trend requires ALL of:
#   - ema50 > ema200       (long-term uptrend)
#   - supertrend_bull      (price above supertrend)
#   - adx > 20             (directional momentum present)
#   - rsi > 60             (strong bullish momentum)
#
# BEAR trend requires ALL of:
#   - ema50 < ema200       (long-term downtrend)
#   - NOT supertrend_bull  (price below supertrend)
#   - adx > 20             (directional momentum present)
#   - rsi < 40             (strong bearish momentum)
#
# If neither condition is fully met, trend = None.
# generate_signals() treats None as no-trade.
# ============================================================

def get_2h_trend(symbol: str, df_30m: pd.DataFrame) -> pd.Series:

    df_2h = fetch_candles(symbol, resolution=RESOLUTION_TREND, limit=CANDLE_LIMIT)
    df_2h = apply_indicators(df_2h)

    # F8: All 4 conditions evaluated per row
    def classify_trend(row):
        bull = (
            row["ema50"]  > row["ema200"] and
            bool(row["supertrend_bull"])  and
            row["adx"]    > 20            and
            row["rsi"]    > 60
        )
        bear = (
            row["ema50"]  < row["ema200"] and
            not bool(row["supertrend_bull"]) and
            row["adx"]    > 20            and
            row["rsi"]    < 40
        )
        if bull:
            return "bull"
        if bear:
            return "bear"
        return None

    df_2h["trend"] = df_2h.apply(classify_trend, axis=1)

    df_2h_trend = df_2h[["timestamp", "trend"]].copy()
    df_30m_ts   = df_30m[["timestamp"]].copy()

    merged = pd.merge_asof(
        df_30m_ts.sort_values("timestamp"),
        df_2h_trend.sort_values("timestamp"),
        on="timestamp",
        direction="backward"
    )

    # F3: ffill() — carry last known trend forward.
    # None values that were never set remain None (no trade).
    merged["trend"] = merged["trend"].ffill()

    trend_series = pd.Series(
        merged["trend"].values,
        index=df_30m.index
    )

    return trend_series

# ============================================================
# SIGNAL GENERATION
# ============================================================

def get_signal(symbol: str):
    """
    Fetch 2H and 30M candles, apply indicators,
    build 2H trend alignment, generate signals.
    Returns (signal_string, latest_price).
    """

    df_30m = fetch_candles(symbol, resolution=RESOLUTION_ENTRY, limit=CANDLE_LIMIT)
    df_30m = apply_indicators(df_30m)

    trend_aligned = get_2h_trend(symbol, df_30m)

    result_df = generate_signals(df_30m, trend_aligned)

    latest_row   = result_df.iloc[-1]
    signal       = latest_row["signal"]
    latest_price = df_30m["close"].iloc[-1]

    if signal == "EXIT_BUY":
        return "EXIT_BUY", latest_price

    if signal == "EXIT_SELL":
        return "EXIT_SELL", latest_price

    if signal == "BUY":
        return "BUY", latest_price

    if signal == "SELL":
        return "SELL", latest_price

    return None, latest_price

# ============================================================
# SINGLE SCAN CYCLE
# ============================================================

def run_once():

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[2H/30M | {current_time}] Scanning symbols...\n")

    for symbol in SYMBOLS:

        try:

            signal, latest_price = get_signal(symbol)

            if signal is None:
                print(f"{symbol} -> No Signal")
                continue

            last_signal = last_signal_map.get(symbol)

            if last_signal == signal:
                print(f"{symbol} -> Duplicate {signal} skipped")
                continue

            if not guard.is_trading_allowed():
                print(f"{symbol} -> Daily loss limit hit")
                continue

            if signal in ("BUY", "SELL"):

                if allocator.is_symbol_active(symbol):
                    print(f"{symbol} -> Active trade exists")
                    continue

                if not allocator.can_open_trade():
                    print(f"{symbol} -> Max trades reached")
                    continue

            size = calculate_position_size(symbol, latest_price)

            print(
                f"{symbol} -> {signal} SIGNAL | "
                f"Price: {latest_price} | Size: {size} lots"
            )

            order = execute_signal(
                symbol=symbol,
                signal=signal,
                market_price=latest_price,
                size=size
            )

            if order:

                print(f"{symbol} -> Order executed")

                if signal in ("BUY", "SELL"):
                    allocator.register_trade(symbol)

                elif signal in ("EXIT_BUY", "EXIT_SELL"):
                    allocator.close_trade(symbol)

                last_signal_map[symbol] = signal

            else:
                print(f"{symbol} -> No execution performed")

        except Exception as e:
            print(f"{symbol} -> ERROR: {e}")

# ============================================================
# STANDALONE LOOP
# ============================================================

def run_live_scanner():

    print("\n================================================")
    print(" LIVE RUNNER STARTED  [2H/30M Strategy]")
    print("================================================\n")

    while True:
        run_once()
        print("\nWaiting for next candle check...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_live_scanner()
