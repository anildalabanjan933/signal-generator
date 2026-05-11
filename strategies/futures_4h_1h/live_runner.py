# ============================================================
# live_runner.py
# ============================================================

import sys
import os
import time
import requests
import pandas as pd
from datetime import datetime

# ----------------------------------------
# PATH FIX - ensures strategy.py is found
# ----------------------------------------
sys.path.insert(0, os.path.dirname(__file__))

from strategy import generate_signals

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

RESOLUTION        = "1h"
CANDLE_LIMIT      = 100          # number of 1H candles to fetch
CHECK_INTERVAL_SECONDS = 300     # check every 5 minutes

last_signal_map = {}

# ============================================================
# LIVE CANDLE FETCHER  (replaces get_mock_dataframe)
# ============================================================

def fetch_candles(symbol: str, resolution: str = "1h", limit: int = 100) -> pd.DataFrame:
    """
    Fetch latest OHLCV candles from Delta Exchange REST API.

    Endpoint : GET /v2/history/candles
    Params   : symbol, resolution, start (unix seconds), end (unix seconds)

    Returns a DataFrame with columns:
        timestamp, open, high, low, close, volume
    """

    end_ts   = int(time.time())
    # Each 1H candle = 3600 seconds
    start_ts = end_ts - (limit * 3600)

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
            raise ValueError(f"API returned success=false for {symbol}: {data}")

        candles = data.get("result", [])

        if not candles:
            raise ValueError(f"No candle data returned for {symbol}")

        df = pd.DataFrame(candles)

        # Rename 'time' -> 'timestamp' to match strategy expectations
        df.rename(columns={"time": "timestamp"}, inplace=True)

        # Keep only required columns
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        # Convert types
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["open"]      = df["open"].astype(float)
        df["high"]      = df["high"].astype(float)
        df["low"]       = df["low"].astype(float)
        df["close"]     = df["close"].astype(float)
        df["volume"]    = df["volume"].astype(float)

        # Sort oldest -> newest, reset index
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

        return df

    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Network error fetching candles for {symbol}: {e}")

    except Exception as e:
        raise RuntimeError(f"Failed to fetch candles for {symbol}: {e}")


# ============================================================
# INDICATOR CALCULATION
# ============================================================

def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate indicators required by strategy.py:
        - rsi
        - ema_fast  (9-period EMA on close)
        - ema_slow  (21-period EMA on close)
        - supertrend_bull (boolean)

    Adjust periods to match your strategy.py settings.
    """

    # --- RSI (14-period) ---
    delta_close = df["close"].diff()
    gain = delta_close.clip(lower=0)
    loss = -delta_close.clip(upper=0)
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # --- EMA fast / slow ---
    df["ema_fast"] = df["close"].ewm(span=9,  adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=21, adjust=False).mean()

    # --- Supertrend (ATR-based, period=10, multiplier=3) ---
    atr_period     = 10
    atr_multiplier = 3.0

    high_low   = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close  = (df["low"]  - df["close"].shift()).abs()
    tr         = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr        = tr.ewm(span=atr_period, adjust=False).mean()

    hl2          = (df["high"] + df["low"]) / 2
    upper_band   = hl2 + (atr_multiplier * atr)
    lower_band   = hl2 - (atr_multiplier * atr)

    supertrend   = [True] * len(df)   # True = bullish

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
# TREND DETECTION (4H proxy from 1H data)
# ============================================================

def get_trend_aligned(df: pd.DataFrame) -> pd.Series:
    """
    Derive a simple 4H trend label from 1H EMA data.
    Returns a Series of 'bull' / 'bear' aligned to df.index.

    Replace this with a real 4H candle fetch if your strategy
    requires a separate 4H timeframe.
    """
    trend = pd.Series(
        ["bull" if fast > slow else "bear"
         for fast, slow in zip(df["ema_fast"], df["ema_slow"])],
        index=df.index
    )
    return trend


# ============================================================
# SIGNAL GENERATION PER SYMBOL
# ============================================================

def get_signal(symbol: str):
    """
    1. Fetch live 1H candles from Delta Exchange
    2. Apply indicators
    3. Run strategy.generate_signals()
    4. Return signal string or None
    """

    # --- Fetch live candles ---
    df_1h = fetch_candles(symbol, resolution=RESOLUTION, limit=CANDLE_LIMIT)

    # --- Apply indicators ---
    df_1h = apply_indicators(df_1h)

    # --- Derive trend ---
    trend_aligned = get_trend_aligned(df_1h)

    # --- Generate signals ---
    result_df = generate_signals(df_1h, trend_aligned)

    latest_row  = result_df.iloc[-1]
    signal      = latest_row["signal"]
    exit_signal = latest_row["exit_signal"]

    # Exit signals take priority
    if exit_signal in ("exit_buy", "exit_sell"):
        return exit_signal.upper()

    if signal == "buy":
        return "BUY"

    if signal == "sell":
        return "SELL"

    return None


# ============================================================
# MAIN LOOP
# ============================================================

def run_live_scanner():

    print("\n================================================")
    print(" LIVE RUNNER STARTED")
    print("================================================\n")

    while True:

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time}] Scanning symbols...\n")

        for symbol in SYMBOLS:

            try:

                signal = get_signal(symbol)

                if signal is None:
                    print(f"{symbol} -> No Signal")
                    continue

                last_signal = last_signal_map.get(symbol)

                if last_signal == signal:
                    print(f"{symbol} -> Duplicate {signal} skipped")
                    continue

                last_signal_map[symbol] = signal
                print(f"{symbol} -> {signal} SIGNAL")

            except Exception as e:
                print(f"{symbol} -> ERROR: {e}")

        print("\nWaiting for next candle check...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_live_scanner()
