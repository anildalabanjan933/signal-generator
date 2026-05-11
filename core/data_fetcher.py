# =================================================
# data_fetcher.py - Delta Exchange Candle Data Fetcher
# Fixes applied:
#   1. Chunk boundary: advance by one candle period to avoid overlap/gap
#   2. Window size capped at 1999 candles to stay safely under the 2000 limit
#   3. Retry logic with exponential backoff on failed/empty chunks
#   4. Retry delay applied correctly on each attempt
#   5. Incomplete last candle excluded (end_time floored to last completed candle)
#   6. Post-fetch range validation with gap detection
#   7. iloc -> loc fix in _validate_candle_range gap logger
#   8. delay_between_requests forwarded through fetch_candles_by_days
#   9. fetch_mtf_candles() added for clean MTF data loading in backtest_engine
# =================================================

import time
import requests
import pandas as pd
from datetime import datetime, timezone

BASE_URL        = "https://api.india.delta.exchange"
CANDLE_ENDPOINT = "/v2/history/candles"

# Supported resolutions as per Delta Exchange API
VALID_RESOLUTIONS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d", "1w"]

# Stay safely under the 2000 candle hard limit per request
MAX_CANDLES_PER_REQUEST = 1999

# Retry configuration
MAX_RETRIES      = 3      # Maximum attempts per chunk
RETRY_BASE_DELAY = 2.0    # Base delay in seconds for exponential backoff


# =================================================
# SECTION 1: Resolution Utilities
# =================================================

def resolution_to_seconds(resolution: str) -> int:
    """
    Convert resolution string to seconds.
    Used to calculate time windows for pagination.
    """
    mapping = {
        "1m":  60,
        "3m":  180,
        "5m":  300,
        "15m": 900,
        "30m": 1800,
        "1h":  3600,
        "2h":  7200,
        "4h":  14400,
        "6h":  21600,
        "1d":  86400,
        "1w":  604800,
    }
    if resolution not in mapping:
        raise ValueError(
            f"Invalid resolution '{resolution}'. "
            f"Valid options: {VALID_RESOLUTIONS}"
        )
    return mapping[resolution]


# =================================================
# SECTION 2: Single Request + Retry
# =================================================

def fetch_candles_single_request(
    symbol: str,
    resolution: str,
    start: int,
    end: int
) -> list | None:
    """
    Fetch up to 1999 candles in a single API call.

    Args:
        symbol     : Trading symbol e.g. 'BTCUSD'
        resolution : Timeframe e.g. '1h', '4h', '1d'
        start      : Unix timestamp in seconds (start time, inclusive)
        end        : Unix timestamp in seconds (end time, inclusive)

    Returns:
        List of raw candle dicts on success.
        None on transient error (caller should retry).
        Empty list [] if API returned success=false (non-retryable).
    """
    params = {
        "symbol":     symbol,
        "resolution": resolution,
        "start":      start,
        "end":        end,
    }

    try:
        response = requests.get(
            BASE_URL + CANDLE_ENDPOINT,
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            print(f"  [WARNING] API returned success=false for {symbol} | "
                  f"start={start} end={end} | Not retrying.")
            return []  # Non-retryable

        return data.get("result", [])

    except requests.exceptions.Timeout:
        print(f"  [ERROR] Request timed out for {symbol} {resolution}. Will retry.")
        return None  # Retryable
    except requests.exceptions.ConnectionError:
        print(f"  [ERROR] Connection error for {symbol} {resolution}. Will retry.")
        return None  # Retryable
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        print(f"  [ERROR] HTTP {status} for {symbol} {resolution}. Will retry.")
        return None  # Retryable
    except Exception as e:
        print(f"  [ERROR] Unexpected error: {e}. Will retry.")
        return None  # Retryable


def fetch_candles_with_retry(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    chunk_index: int
) -> list:
    """
    Wraps fetch_candles_single_request with exponential backoff retry logic.

    Args:
        symbol      : Trading symbol
        resolution  : Timeframe string
        start       : Chunk start unix timestamp (seconds)
        end         : Chunk end unix timestamp (seconds)
        chunk_index : Chunk number for logging

    Returns:
        List of candle dicts. Empty list if all retries exhausted.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        result = fetch_candles_single_request(symbol, resolution, start, end)

        if result is None:
            # Transient error — exponential backoff: 2s, 4s, 8s
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            print(f"  [CHUNK {chunk_index}] Attempt {attempt}/{MAX_RETRIES} failed. "
                  f"Retrying in {wait:.1f}s...")
            time.sleep(wait)
            continue

        if result == []:
            # API returned success=false — non-retryable
            return []

        # Success
        if attempt > 1:
            print(f"  [CHUNK {chunk_index}] Succeeded on attempt {attempt}.")
        return result

    print(f"  [CHUNK {chunk_index}] All {MAX_RETRIES} attempts failed. "
          f"This time window will have missing data.")
    return []


# =================================================
# SECTION 3: Core Paginated Fetcher
# =================================================

def fetch_candles(
    symbol: str,
    resolution: str,
    start_time: int,
    end_time: int,
    delay_between_requests: float = 0.3
) -> pd.DataFrame:
    """
    Fetch historical candles with automatic pagination, retry logic,
    boundary-safe chunking, and post-fetch validation.

    Args:
        symbol                 : Trading symbol e.g. 'BTCUSD'
        resolution             : Timeframe e.g. '1h', '4h', '1d'
        start_time             : Unix timestamp in seconds
        end_time               : Unix timestamp in seconds
        delay_between_requests : Seconds to wait between paginated calls

    Returns:
        pandas DataFrame with columns:
        [time, open, high, low, close, volume, datetime]
        Sorted ascending by time. Empty DataFrame if fetch fails.
    """

    # --- Validate resolution ---
    if resolution not in VALID_RESOLUTIONS:
        print(f"[ERROR] Invalid resolution '{resolution}'. "
              f"Valid: {VALID_RESOLUTIONS}")
        return pd.DataFrame()

    # --- Validate time range ---
    if start_time >= end_time:
        print(f"[ERROR] start_time must be less than end_time.")
        return pd.DataFrame()

    candle_seconds = resolution_to_seconds(resolution)

    # Fix #5: Floor end_time to the last fully completed candle boundary.
    # Prevents the currently-forming (incomplete) candle from being included.
    now           = int(time.time())
    safe_end_time = min(end_time, now - candle_seconds)
    safe_end_time = (safe_end_time // candle_seconds) * candle_seconds

    if safe_end_time <= start_time:
        print(f"[ERROR] After flooring to completed candles, "
              f"safe_end_time ({safe_end_time}) <= start_time ({start_time}). "
              f"No completed candles available in this range.")
        return pd.DataFrame()

    # Window size in seconds: 1999 candles per chunk
    window_size    = MAX_CANDLES_PER_REQUEST * candle_seconds
    all_candles    = []
    chunk_start    = start_time
    total_requests = 0
    failed_chunks  = 0

    print(f"\n[INFO] Fetching {symbol} | {resolution} | "
          f"{datetime.fromtimestamp(start_time, tz=timezone.utc).strftime('%Y-%m-%d')} "
          f"to "
          f"{datetime.fromtimestamp(safe_end_time, tz=timezone.utc).strftime('%Y-%m-%d')}")

    # --- Paginate through time range in chunks ---
    while chunk_start < safe_end_time:
        chunk_end = min(chunk_start + window_size, safe_end_time)

        candles = fetch_candles_with_retry(
            symbol=symbol,
            resolution=resolution,
            start=chunk_start,
            end=chunk_end,
            chunk_index=total_requests + 1
        )

        total_requests += 1

        if candles:
            all_candles.extend(candles)
            print(f"  [CHUNK {total_requests}] "
                  f"{datetime.fromtimestamp(chunk_start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
                  f"-> "
                  f"{datetime.fromtimestamp(chunk_end, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
                  f"| Got {len(candles)} candles")
        else:
            failed_chunks += 1
            print(f"  [CHUNK {total_requests}] "
                  f"{datetime.fromtimestamp(chunk_start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
                  f"-> "
                  f"{datetime.fromtimestamp(chunk_end, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
                  f"| NO DATA after all retries.")

        # Fix #1: Advance by chunk_end + one candle period to avoid
        # boundary overlap or gap.
        chunk_start = chunk_end + candle_seconds

        # Pace requests to respect rate limits
        if chunk_start < safe_end_time:
            time.sleep(delay_between_requests)

    # --- Build DataFrame ---
    if not all_candles:
        print(f"[WARNING] No candles fetched for {symbol} {resolution}.")
        return pd.DataFrame()

    df = pd.DataFrame(all_candles)

    # Ensure correct column types
    df["time"]   = pd.to_numeric(df["time"],   errors="coerce")
    df["open"]   = pd.to_numeric(df["open"],   errors="coerce")
    df["high"]   = pd.to_numeric(df["high"],   errors="coerce")
    df["low"]    = pd.to_numeric(df["low"],    errors="coerce")
    df["close"]  = pd.to_numeric(df["close"],  errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    # Drop rows with missing critical OHLC data
    df.dropna(subset=["time", "open", "high", "low", "close"], inplace=True)

    # Remove duplicate candles (can occur at chunk boundaries)
    df.drop_duplicates(subset=["time"], inplace=True)

    # Sort ascending by time (oldest first)
    df.sort_values("time", ascending=True, inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Add human-readable datetime column (UTC-aware)
    df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)

    print(f"[INFO] Total candles fetched : {len(df)} | "
          f"Requests made : {total_requests} | "
          f"Failed chunks : {failed_chunks}")

    # Fix #6: Post-fetch range validation and gap detection
    _validate_candle_range(df, start_time, safe_end_time, candle_seconds, symbol, resolution)

    return df


# =================================================
# SECTION 4: Post-Fetch Validation
# =================================================

def _validate_candle_range(
    df: pd.DataFrame,
    expected_start: int,
    expected_end: int,
    candle_seconds: int,
    symbol: str,
    resolution: str
) -> None:
    """
    Fix #6 + Fix #7: Validate fetched DataFrame covers the expected time range
    and check for unexpected internal gaps larger than one candle period.
    Uses .loc instead of .iloc for safe index-based access after reset_index.

    Args:
        df             : Fetched candle DataFrame (sorted ascending, reset index)
        expected_start : Requested start unix timestamp (seconds)
        expected_end   : Requested end unix timestamp (seconds, floored)
        candle_seconds : Duration of one candle in seconds
        symbol         : Symbol name for logging
        resolution     : Resolution string for logging
    """
    if df.empty:
        return

    actual_start = int(df["time"].iloc[0])
    actual_end   = int(df["time"].iloc[-1])

    # Allow up to 2 candle periods of tolerance at boundaries
    tolerance = candle_seconds * 2

    if actual_start > expected_start + tolerance:
        print(f"  [VALIDATION WARNING] {symbol} {resolution}: "
              f"Data starts at "
              f"{datetime.fromtimestamp(actual_start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
              f"but expected start was "
              f"{datetime.fromtimestamp(expected_start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}. "
              f"Early data may be missing.")

    if actual_end < expected_end - tolerance:
        print(f"  [VALIDATION WARNING] {symbol} {resolution}: "
              f"Data ends at "
              f"{datetime.fromtimestamp(actual_end, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
              f"but expected end was "
              f"{datetime.fromtimestamp(expected_end, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}. "
              f"Recent data may be missing.")

    # Detect internal gaps larger than 3x the candle period
    # (3x tolerance accounts for legitimate low-volume periods)
    gap_threshold = candle_seconds * 3
    time_diffs    = df["time"].diff().dropna()
    large_gaps    = time_diffs[time_diffs > gap_threshold]

    if not large_gaps.empty:
        print(f"  [VALIDATION WARNING] {symbol} {resolution}: "
              f"Detected {len(large_gaps)} internal gap(s) larger than "
              f"{gap_threshold // candle_seconds} candle periods:")

        # Fix #7: Use .loc instead of .iloc — safe after reset_index(drop=True)
        # large_gaps.index contains integer labels matching df.index exactly
        for idx in large_gaps.index:
            gap_start = int(df.loc[idx - 1, "time"])
            gap_end   = int(df.loc[idx, "time"])
            gap_size  = int(large_gaps[idx]) // candle_seconds
            print(f"    Gap of {gap_size} candles between "
                  f"{datetime.fromtimestamp(gap_start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')} "
                  f"and "
                  f"{datetime.fromtimestamp(gap_end, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    else:
        print(f"  [VALIDATION OK] {symbol} {resolution}: No significant gaps detected.")


# =================================================
# SECTION 5: Public Convenience Wrappers
# =================================================

def fetch_candles_by_days(
    symbol: str,
    resolution: str,
    days: int,
    delay_between_requests: float = 0.3   # Fix #8: now forwarded to fetch_candles
) -> pd.DataFrame:
    """
    Convenience wrapper — fetch last N days of candles.
    Fix #5: end_time is set to now; fetch_candles() floors it
    to the last completed candle boundary automatically.
    Fix #8: delay_between_requests is now forwarded to fetch_candles().

    Args:
        symbol                 : Trading symbol e.g. 'BTCUSD'
        resolution             : Timeframe e.g. '1h', '4h', '1d'
        days                   : Number of past days to fetch
        delay_between_requests : Seconds between paginated API calls

    Returns:
        pandas DataFrame (same format as fetch_candles)
    """
    end_time   = int(time.time())
    start_time = end_time - (days * 86400)

    return fetch_candles(
        symbol=symbol,
        resolution=resolution,
        start_time=start_time,
        end_time=end_time,
        delay_between_requests=delay_between_requests   # Fix #8
    )


def fetch_mtf_candles(
    symbol: str,
    days: int,
    trend_resolution: str = "4h",
    entry_resolution: str = "1h",
    delay_between_requests: float = 0.3
) -> dict:
    """
    Fix #9: Fetch both trend (4H) and entry (1H) candles for MTF strategy
    in a single call. Keeps backtest.py clean.

    Usage in backtest.py:
        data   = fetch_mtf_candles("BTCUSD", days=730)
        df_4h  = data["trend"]
        df_1h  = data["entry"]

    Args:
        symbol                 : Trading symbol e.g. 'BTCUSD'
        days                   : Number of past days to fetch
        trend_resolution       : Higher timeframe for trend filter (default: '4h')
        entry_resolution       : Lower timeframe for entry signals (default: '1h')
        delay_between_requests : Seconds between paginated API calls

    Returns:
        dict with keys:
            "trend"  -> pd.DataFrame (4H candles)
            "entry"  -> pd.DataFrame (1H candles)
        Either DataFrame may be empty if fetch fails — caller must check.
    """
    print(f"\n{'='*55}")
    print(f"[MTF FETCH] {symbol} | "
          f"Trend TF: {trend_resolution} | Entry TF: {entry_resolution} | "
          f"Days: {days}")
    print(f"{'='*55}")

    # Fetch trend timeframe (4H)
    df_trend = fetch_candles_by_days(
        symbol=symbol,
        resolution=trend_resolution,
        days=days,
        delay_between_requests=delay_between_requests
    )

    # Fetch entry timeframe (1H)
    df_entry = fetch_candles_by_days(
        symbol=symbol,
        resolution=entry_resolution,
        days=days,
        delay_between_requests=delay_between_requests
    )

    # Summary
    print(f"\n[MTF SUMMARY] {symbol}")
    if not df_trend.empty:
        print(f"  Trend ({trend_resolution}) : {len(df_trend)} candles | "
              f"{df_trend['datetime'].iloc[0].strftime('%Y-%m-%d')} "
              f"-> {df_trend['datetime'].iloc[-1].strftime('%Y-%m-%d')}")
    else:
        print(f"  [ERROR] Trend ({trend_resolution}) : FAILED — no data returned.")

    if not df_entry.empty:
        print(f"  Entry ({entry_resolution}) : {len(df_entry)} candles | "
              f"{df_entry['datetime'].iloc[0].strftime('%Y-%m-%d')} "
              f"-> {df_entry['datetime'].iloc[-1].strftime('%Y-%m-%d')}")
    else:
        print(f"  [ERROR] Entry ({entry_resolution}) : FAILED — no data returned.")

    return {
        "trend": df_trend,
        "entry": df_entry
    }


# =================================================
# SECTION 6: Quick Test
# Run this file directly to verify connectivity
# and pagination for both MTF resolutions.
# =================================================

if __name__ == "__main__":

    print("\n" + "="*55)
    print("  data_fetcher.py — Self Test")
    print("="*55)

    # Test 1: Single resolution fetch (30 days, 4H)
    print("\n[TEST 1] Single fetch — BTCUSD 4H — last 30 days")
    df = fetch_candles_by_days(
        symbol="BTCUSD",
        resolution="4h",
        days=30
    )
    if not df.empty:
        print(f"\n  Sample (last 5 rows):")
        print(df[["datetime", "open", "high", "low", "close", "volume"]].tail(5).to_string())
        print(f"\n  Total rows : {len(df)}")
        print(f"  Date range : {df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}")
    else:
        print("  [FAIL] No data returned. Check symbol and connection.")

    # Test 2: MTF fetch (30 days, both 4H and 1H)
    print("\n[TEST 2] MTF fetch — BTCUSD — last 30 days")
    mtf = fetch_mtf_candles(
        symbol="BTCUSD",
        days=30,
        trend_resolution="4h",
        entry_resolution="1h"
    )
    print(f"\n  Trend rows : {len(mtf['trend'])}")
    print(f"  Entry rows : {len(mtf['entry'])}")

    # Test 3: Invalid resolution guard
    print("\n[TEST 3] Invalid resolution guard")
    df_bad = fetch_candles_by_days(
        symbol="BTCUSD",
        resolution="2d",   # Not a valid resolution
        days=10
    )
    print(f"  Returned empty: {df_bad.empty}")  # Should be True
