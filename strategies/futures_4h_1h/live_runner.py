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

# ----------------------------------------
# EXECUTION + RISK
# ----------------------------------------
from execution.demo_executor import execute_signal
from risk.daily_guard import DailyGuard
from risk.trade_allocator import TradeAllocator

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

RESOLUTION = "1h"
CANDLE_LIMIT = 100
CHECK_INTERVAL_SECONDS = 300

last_signal_map = {}

# ============================================================
# LIVE CANDLE FETCHER
# ============================================================

def fetch_candles(
    symbol: str,
    resolution: str = "1h",
    limit: int = 100
) -> pd.DataFrame:

    end_ts = int(time.time())
    start_ts = end_ts - (limit * 3600)

    url = f"{BASE_URL}/v2/history/candles"

    params = {
        "symbol": symbol,
        "resolution": resolution,
        "start": start_ts,
        "end": end_ts,
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            raise ValueError(
                f"API returned success=false for {symbol}"
            )

        candles = data.get("result", [])

        if not candles:
            raise ValueError(
                f"No candle data for {symbol}"
            )

        df = pd.DataFrame(candles)

        df.rename(
            columns={"time": "timestamp"},
            inplace=True
        )

        df = df[
            [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="s",
            utc=True
        )

        for col in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:
            df[col] = df[col].astype(float)

        df.sort_values(
            "timestamp",
            inplace=True
        )

        df.reset_index(
            drop=True,
            inplace=True
        )

        return df

    except requests.exceptions.RequestException as e:
        raise ConnectionError(
            f"Network error for {symbol}: {e}"
        )

    except Exception as e:
        raise RuntimeError(
            f"Failed fetching candles for {symbol}: {e}"
        )

# ============================================================
# INDICATORS
# ============================================================

def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:

    # RSI
    delta_close = df["close"].diff()

    gain = delta_close.clip(lower=0)
    loss = -delta_close.clip(upper=0)

    avg_gain = gain.ewm(
        com=13,
        min_periods=14
    ).mean()

    avg_loss = loss.ewm(
        com=13,
        min_periods=14
    ).mean()

    rs = avg_gain / avg_loss

    df["rsi"] = 100 - (100 / (1 + rs))

    # EMA
    df["ema_fast"] = df["close"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["ema_slow"] = df["close"].ewm(
        span=21,
        adjust=False
    ).mean()

    # Supertrend
    atr_period = 10
    atr_multiplier = 3.0

    high_low = df["high"] - df["low"]

    high_close = (
        df["high"] - df["close"].shift()
    ).abs()

    low_close = (
        df["low"] - df["close"].shift()
    ).abs()

    tr = pd.concat(
        [high_low, high_close, low_close],
        axis=1
    ).max(axis=1)

    atr = tr.ewm(
        span=atr_period,
        adjust=False
    ).mean()

    hl2 = (df["high"] + df["low"]) / 2

    upper_band = hl2 + (
        atr_multiplier * atr
    )

    lower_band = hl2 - (
        atr_multiplier * atr
    )

    supertrend = [True] * len(df)

    for i in range(1, len(df)):

        if df["close"].iloc[i] > upper_band.iloc[i]:
            supertrend[i] = True

        elif df["close"].iloc[i] < lower_band.iloc[i]:
            supertrend[i] = False

        else:
            supertrend[i] = supertrend[i - 1]

    df["supertrend_bull"] = pd.array(
        supertrend,
        dtype="boolean"
    )

    return df

# ============================================================
# TREND DETECTION
# ============================================================

def get_trend_aligned(
    df: pd.DataFrame
) -> pd.Series:

    trend = pd.Series(
        [
            "bull"
            if fast > slow
            else "bear"
            for fast, slow in zip(
                df["ema_fast"],
                df["ema_slow"]
            )
        ],
        index=df.index
    )

    return trend

# ============================================================
# SIGNAL GENERATION
# ============================================================

def get_signal(symbol: str):

    df_1h = fetch_candles(
        symbol,
        resolution=RESOLUTION,
        limit=CANDLE_LIMIT
    )

    df_1h = apply_indicators(df_1h)

    trend_aligned = get_trend_aligned(df_1h)

    result_df = generate_signals(
        df_1h,
        trend_aligned
    )

    latest_row = result_df.iloc[-1]

    signal = latest_row["signal"]
    exit_signal = latest_row["exit_signal"]

    # Exit signals priority
    if exit_signal in (
        "exit_buy",
        "exit_sell"
    ):
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

    guard = DailyGuard()
    allocator = TradeAllocator()

    while True:

        current_time = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        print(f"\n[{current_time}] Scanning symbols...\n")

        for symbol in SYMBOLS:

            try:

                signal = get_signal(symbol)

                # ------------------------------------------------
                # LATEST PRICE FOR POSITION SIZING
                # ------------------------------------------------

                df_price = fetch_candles(
                    symbol,
                    resolution=RESOLUTION,
                    limit=2
                )

                latest_price = df_price["close"].iloc[-1]

                if signal is None:
                    print(f"{symbol} -> No Signal")
                    continue

                # Duplicate signal protection
                last_signal = last_signal_map.get(symbol)

                if last_signal == signal:
                    print(
                        f"{symbol} -> Duplicate {signal} skipped"
                    )
                    continue

                # Daily guard
                if not guard.is_trading_allowed():
                    print(
                        f"{symbol} -> Daily loss limit hit"
                    )
                    continue

                # Entry signals
                if signal in ("BUY", "SELL"):

                    if allocator.is_symbol_active(symbol):
                        print(
                            f"{symbol} -> Active trade exists"
                        )
                        continue

                    if not allocator.can_open_trade():
                        print(
                            f"{symbol} -> Max trades reached"
                        )
                        continue

                # Execute
                print(f"{symbol} -> {signal} SIGNAL")

                order = execute_signal(
                    symbol=symbol,
                    signal=signal,
                    market_price=latest_price
                )

                if order:

                    print(
                        f"{symbol} -> Order executed"
                    )

                    # Register trade
                    if signal in ("BUY", "SELL"):

                        allocator.register_trade(symbol)

                    elif signal in (
                        "EXIT_BUY",
                        "EXIT_SELL"
                    ):

                        allocator.close_trade(symbol)

                    last_signal_map[symbol] = signal

                else:

                    print(
                        f"{symbol} -> No execution performed"
                    )

            except Exception as e:

                print(f"{symbol} -> ERROR: {e}")

        print("\nWaiting for next candle check...\n")

        time.sleep(CHECK_INTERVAL_SECONDS)

# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_live_scanner()