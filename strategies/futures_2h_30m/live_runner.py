# ============================================================
# live_runner.py  -  futures_2h_30m strategy
# ============================================================
# Timeframe structure:
#   2H candles  ->  trend direction (EMA9/EMA21 + Supertrend)
#   30M candles ->  entry signal    (RSI cross, EMA, Supertrend exit)
#
# FIXES APPLIED:
#   F1 - get_signal() signal checks corrected to uppercase.
#        "buy"/"sell"/"exit_buy"/"exit_sell" were lowercase.
#        strategy.py was fixed to emit uppercase signals.
#        live_runner must match. Mismatch caused zero executions.
#   F2 - exit_signal separate column removed from get_signal().
#        strategy.py fix merged exit_signal into signal column.
#        Reading latest_row["exit_signal"] would throw KeyError.
#        Now only signal column is read. EXIT_BUY/EXIT_SELL
#        arrive in signal column directly.
#   F3 - fillna(method="ffill") replaced with ffill().
#        pandas deprecated the method= argument.
#        Use df.ffill() directly to avoid FutureWarning.
#   F4 - guard and allocator moved to module level.
#        Were inside run_live_scanner() only.
#        run_once() needs access to same instances so
#        daily PnL and active trade count persist across
#        calls from scanner.py coordinator.
#   F5 - run_once() added for scanner.py coordinator.
#        scanner.py calls run_once() on a schedule.
#        run_live_scanner() kept for standalone use.
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
# State must persist across run_once() calls so daily PnL
# and active trade count are not reset on every scan cycle.
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
# ============================================================

def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:

    # ---- RSI ----
    delta_close = df["close"].diff()
    gain        = delta_close.clip(lower=0)
    loss        = -delta_close.clip(upper=0)
    avg_gain    = gain.ewm(com=13, min_periods=14).mean()
    avg_loss    = loss.ewm(com=13, min_periods=14).mean()
    rs          = avg_gain / avg_loss
    df["rsi"]   = 100 - (100 / (1 + rs))

    # ---- EMA ----
    df["ema_fast"] = df["close"].ewm(span=9,  adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()

    # ---- Supertrend ----
    atr_period     = 10
    atr_multiplier = 3.0

    high_low   = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close  = (df["low"]  - df["close"].shift()).abs()

    tr  = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(span=atr_period, adjust=False).mean()

    hl2        = (df["high"] + df["low"]) / 2
    upper_band = hl2 + (atr_multiplier * atr)
    lower_band = hl2 - (atr_multiplier * atr)

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
# ============================================================

def get_2h_trend(symbol: str, df_30m: pd.DataFrame) -> pd.Series:

    df_2h = fetch_candles(symbol, resolution=RESOLUTION_TREND, limit=CANDLE_LIMIT)
    df_2h = apply_indicators(df_2h)

    df_2h["trend"] = df_2h.apply(
        lambda row: "bull" if row["ema_fast"] > row["ema_slow"] else "bear",
        axis=1
    )

    df_2h_trend = df_2h[["timestamp", "trend"]].copy()
    df_30m_ts   = df_30m[["timestamp"]].copy()

    merged = pd.merge_asof(
        df_30m_ts.sort_values("timestamp"),
        df_2h_trend.sort_values("timestamp"),
        on="timestamp",
        direction="backward"
    )

    # F3: replaced fillna(method="ffill") with ffill()
    merged["trend"] = merged["trend"].ffill().fillna("bear")

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

    F1: All signal comparisons corrected to uppercase.
        strategy.py emits BUY/SELL/EXIT_BUY/EXIT_SELL.
    F2: exit_signal column removed. EXIT_BUY and EXIT_SELL
        now arrive in the signal column directly.
    """

    df_30m = fetch_candles(symbol, resolution=RESOLUTION_ENTRY, limit=CANDLE_LIMIT)
    df_30m = apply_indicators(df_30m)

    trend_aligned = get_2h_trend(symbol, df_30m)

    result_df = generate_signals(df_30m, trend_aligned)

    latest_row   = result_df.iloc[-1]
    signal       = latest_row["signal"]      # F2: single column only
    latest_price = df_30m["close"].iloc[-1]

    # F1: all comparisons uppercase to match strategy.py output
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
# F5: Called by scanner.py coordinator on schedule.
#     No loop, no sleep. Scans all symbols once and returns.
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
# Kept for running this file directly.
# scanner.py uses run_once() instead.
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
