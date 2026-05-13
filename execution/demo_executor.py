# ============================================================
# execution/demo_executor.py
#
# Delta Exchange DEMO (Testnet) Executor
# Connects to: https://cdn-ind.testnet.deltaex.org
#
# Supports : BTCUSD, ETHUSD, SOLUSD, BNBUSD, DOGEUSD
# Orders   : Market orders only
# Account  : DEMO / Testnet only — no live funds
#
# FIXES APPLIED:
#   F1 - _request() query string double-append fixed.
#        Original code built query_string manually AND passed
#        params=params to requests.request(). This caused the
#        query string to be appended twice to the URL, making
#        the actual request URL differ from the signed URL.
#        Fix: build query_string for signature only, pass
#        params=None to requests and use the full URL directly.
#
#   F2 - place_order() now accepts reduce_only parameter.
#        Was hardcoded absent from the order body.
#        Exit orders (EXIT_BUY, EXIT_SELL) must use
#        reduce_only="true" to prevent accidental position
#        flip if the position was already closed externally
#        (liquidation, manual close, etc.).
#
#   F3 - execute_signal() now passes reduce_only="true"
#        for EXIT_BUY and EXIT_SELL signals.
#        Entry signals (BUY, SELL) pass reduce_only="false".
#        This is the correct and safe behaviour for all cases.
#
#   F4 - SYMBOL_CONFIG fallback_size values aligned to
#        roadmap position sizing ($15 margin, 20x leverage).
#        These are only used when live_runner does not pass
#        a size argument. Values are conservative minimums.
# ============================================================

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

import requests

# ============================================================
# LOG DIRECTORY
# Relative to this file's location, not the working directory
# ============================================================

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, "demo_executor.log")),
    ],
)

logger = logging.getLogger("DemoExecutor")

# ============================================================
# CONFIG
# ============================================================

# Demo / Testnet base URL — never points to live account
DEMO_BASE_URL = "https://cdn-ind.testnet.deltaex.org"

# Load credentials from environment variables ONLY.
# Never hardcode credentials in source code.
# Set DEMO_API_KEY and DEMO_API_SECRET in your .env file
# or Railway environment settings.
DEMO_API_KEY    = os.environ.get("To84nCnFuwhFh1w6c0QQmwyZTmk1KR", "")
DEMO_API_SECRET = os.environ.get("2b7YvlMfj9lhdeIfXxZ1QQf4h8xu5sSifnWkb4vsjondFgssGnMgJikiC7OA", "")

if not DEMO_API_KEY or not DEMO_API_SECRET:
    raise EnvironmentError(
        "DEMO_API_KEY and DEMO_API_SECRET must be set as environment variables. "
        "Add them to your .env file or Railway environment settings."
    )

# Supported symbols and their fallback order sizes (in lots/contracts).
# These are only used if execute_signal() is called without a size argument.
# In normal operation, live_runner.py always passes size from position_sizer.py.
#
# F4: Fallback sizes aligned to roadmap ($15 margin, 20x leverage = $300 notional).
# These are conservative minimums — actual sizes come from position_sizer.py.
#
# Contract values verified from Delta Exchange API (May 2026):
#   BTCUSD  : 0.001 BTC/lot  — at ~$103,000: $300 / ($103,000 * 0.001) = ~2 lots
#   ETHUSD  : 0.01  ETH/lot  — at ~$2,400:   $300 / ($2,400   * 0.01)  = ~12 lots
#   SOLUSD  : 1     SOL/lot  — at ~$170:      $300 / ($170     * 1)     = ~1 lot
#   BNBUSD  : 0.1   BNB/lot  — at ~$650:      $300 / ($650     * 0.1)   = ~4 lots
#   DOGEUSD : 100   DOGE/lot — at ~$0.22:     $300 / ($0.22    * 100)   = ~13 lots
SYMBOL_CONFIG = {
    "BTCUSD" : {"fallback_size": 2},
    "ETHUSD" : {"fallback_size": 12},
    "SOLUSD" : {"fallback_size": 1},
    "BNBUSD" : {"fallback_size": 4},
    "DOGEUSD": {"fallback_size": 13},
}

# Request timeout: (connect_timeout, read_timeout) in seconds
REQUEST_TIMEOUT = (3, 27)

# ============================================================
# AUTHENTICATION
# ============================================================

def _generate_signature(secret: str, message: str) -> str:
    """
    Generate HMAC-SHA256 signature for Delta Exchange API authentication.

    Signature formula:
        HMAC_SHA256(secret, method + timestamp + path + query_string + body)

    Note: query_string must include the leading "?" if present.
          e.g. "?contract_types=perpetual_futures"
    """
    return hmac.new(
        bytes(secret, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_headers(
    method      : str,
    path        : str,
    query_string: str = "",
    body        : str = ""
) -> dict:
    """
    Build authenticated request headers.

    Required headers for all authenticated Delta Exchange requests:
        api-key      : Your API key
        timestamp    : Current unix timestamp (seconds)
        signature    : HMAC-SHA256 of (method + timestamp + path + query_string + body)
        User-Agent   : Client identifier
        Content-Type : application/json

    Args:
        method       : HTTP method e.g. "GET", "POST"
        path         : API path e.g. "/v2/orders"
        query_string : Full query string including "?" e.g. "?contract_types=perpetual_futures"
        body         : JSON-serialised request body string, or "" for GET requests
    """
    timestamp      = str(int(time.time()))
    signature_data = method + timestamp + path + query_string + body
    signature      = _generate_signature(DEMO_API_SECRET, signature_data)

    return {
        "api-key"     : DEMO_API_KEY,
        "timestamp"   : timestamp,
        "signature"   : signature,
        "User-Agent"  : "python-demo-executor",
        "Content-Type": "application/json",
    }


# ============================================================
# CORE HTTP HELPER
# ============================================================

def _request(
    method: str,
    path  : str,
    params: dict = None,
    body  : dict = None
) -> dict:
    """
    Execute an authenticated HTTP request against the Demo API.

    Args:
        method : HTTP method ("GET" or "POST")
        path   : API path, e.g. "/v2/orders"
        params : Query parameters dict (for GET requests)
        body   : Request body dict (for POST requests)

    Returns:
        Parsed JSON response dict

    Raises:
        ConnectionError : On network-level failures
        ValueError      : When API returns success=false
        RuntimeError    : On unexpected errors

    F1 FIX — Query string handling:
        The signature must be computed over the query string
        exactly as it appears in the URL. Previously, query_string
        was built manually for the signature AND params was also
        passed to requests, causing it to be appended twice.
        Fix: build query_string for signature computation only,
        then construct the full URL manually and pass params=None
        to requests so the URL is not modified by the library.
    """
    body_str     = ""
    query_string = ""

    # Build query string for signature (must match URL exactly)
    if params:
        query_string = "?" + "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )

    if body:
        body_str = json.dumps(body, separators=(",", ":"))

    headers = _build_headers(method, path, query_string, body_str)

    # F1: Construct full URL manually. Pass params=None to requests
    # so the library does not append the query string a second time,
    # which would cause the actual URL to differ from the signed URL.
    full_url = f"{DEMO_BASE_URL}{path}{query_string}"

    try:
        response = requests.request(
            method,
            full_url,
            headers = headers,
            params  = None,           # F1: never pass params here
            data    = body_str if body_str else None,
            timeout = REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            error_detail = result.get("error", result)
            raise ValueError(f"API error on {method} {path}: {error_detail}")

        return result

    except requests.exceptions.Timeout as e:
        raise ConnectionError(f"Request timed out for {method} {path}: {e}")

    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(f"Network connection failed for {method} {path}: {e}")

    except requests.exceptions.HTTPError as e:
        raise RuntimeError(
            f"HTTP error {response.status_code} for {method} {path}: {e}"
        )

    except ValueError:
        raise

    except Exception as e:
        raise RuntimeError(f"Unexpected error on {method} {path}: {e}")


# ============================================================
# SYMBOL VALIDATION
# ============================================================

def _validate_symbol(symbol: str) -> None:
    """
    Raise ValueError if symbol is not in the supported list.
    """
    if symbol not in SYMBOL_CONFIG:
        supported = ", ".join(SYMBOL_CONFIG.keys())
        raise ValueError(
            f"Symbol '{symbol}' is not supported. "
            f"Supported symbols: {supported}"
        )


# ============================================================
# PLACE ORDER
# ============================================================

def place_order(
    symbol     : str,
    side       : str,
    size       : Optional[int] = None,
    reduce_only: str           = "false"
) -> dict:
    """
    Place a market order on the Delta Exchange Demo account.

    Args:
        symbol      : Trading symbol, e.g. "BTCUSD"
        side        : "buy" or "sell"
        size        : Order size in lots/contracts.
                      If None, uses fallback_size from SYMBOL_CONFIG.
        reduce_only : "true" for exit/close orders, "false" for entry orders.
                      F2: Added parameter — was missing entirely.
                      When "true", order is rejected if no position exists
                      to close, preventing accidental position flip.

    Returns:
        Order response dict from the API.

    Raises:
        ValueError      : Invalid symbol or side
        ConnectionError : Network failure
        RuntimeError    : API or unexpected error
    """
    _validate_symbol(symbol)

    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid side '{side}'. Must be 'buy' or 'sell'.")

    if reduce_only not in ("true", "false"):
        raise ValueError(
            f"Invalid reduce_only '{reduce_only}'. Must be 'true' or 'false'."
        )

    # Use provided size or fall back to SYMBOL_CONFIG fallback
    order_size = size if size is not None else SYMBOL_CONFIG[symbol]["fallback_size"]

    if order_size <= 0:
        raise ValueError(
            f"Order size must be a positive integer. Got: {order_size}"
        )

    path = "/v2/orders"
    body = {
        "product_symbol": symbol,
        "side"          : side,
        "size"          : order_size,
        "order_type"    : "market_order",
        "reduce_only"   : reduce_only,   # F2: now included in every order
    }

    logger.info(
        f"Placing DEMO market order | "
        f"Symbol: {symbol} | Side: {side.upper()} | "
        f"Size: {order_size} | reduce_only: {reduce_only}"
    )

    try:
        response = _request("POST", path, body=body)
        order    = response.get("result", {})

        logger.info(
            f"Order placed successfully | "
            f"ID: {order.get('id')} | "
            f"Symbol: {order.get('product_symbol')} | "
            f"Side: {order.get('side', '').upper()} | "
            f"Size: {order.get('size')} | "
            f"State: {order.get('state')}"
        )

        return order

    except (ValueError, ConnectionError, RuntimeError) as e:
        logger.error(f"Failed to place order for {symbol} {side.upper()}: {e}")
        raise


# ============================================================
# GET OPEN POSITIONS
# ============================================================

def get_open_positions(symbol: str = None) -> list:
    """
    Fetch open positions from the Delta Exchange Demo account.

    Args:
        symbol : Optional. Filter results to a specific symbol.
                 If None, returns all open perpetual futures positions.

    Returns:
        List of position dicts.

    Raises:
        ConnectionError : Network failure
        RuntimeError    : API or unexpected error
    """
    if symbol:
        _validate_symbol(symbol)

    path   = "/v2/positions/margined"
    params = {"contract_types": "perpetual_futures"}

    logger.info(
        f"Fetching open positions | "
        f"Filter: {symbol if symbol else 'ALL perpetual_futures'}"
    )

    try:
        response  = _request("GET", path, params=params)
        positions = response.get("result", [])

        if symbol:
            positions = [
                p for p in positions
                if p.get("product_symbol") == symbol
            ]

        if positions:
            for pos in positions:
                direction = "LONG" if pos.get("size", 0) > 0 else "SHORT"
                logger.info(
                    f"Open position | "
                    f"Symbol: {pos.get('product_symbol')} | "
                    f"Direction: {direction} | "
                    f"Size: {pos.get('size')} | "
                    f"Entry: {pos.get('entry_price')} | "
                    f"Liq Price: {pos.get('liquidation_price')} | "
                    f"Realized PnL: {pos.get('realized_pnl')}"
                )
        else:
            logger.info(
                f"No open positions found"
                f"{' for ' + symbol if symbol else ''}"
            )

        return positions

    except (ValueError, ConnectionError, RuntimeError) as e:
        logger.error(f"Failed to fetch positions: {e}")
        raise


# ============================================================
# EXECUTE SIGNAL
# Primary integration point for live_runner.py
# ============================================================

def execute_signal(
    symbol      : str,
    signal      : str,
    market_price: float         = None,
    size        : Optional[int] = None
) -> Optional[dict]:
    """
    Translate a strategy signal into a demo market order.

    Signal mapping:
        "BUY"        -> place_order(symbol, "buy",  size, reduce_only="false")
        "SELL"       -> place_order(symbol, "sell", size, reduce_only="false")
        "EXIT_BUY"   -> place_order(symbol, "sell", size, reduce_only="true")
        "EXIT_SELL"  -> place_order(symbol, "buy",  size, reduce_only="true")
        None / other -> no action

    F3: EXIT signals now pass reduce_only="true".
        If the position was already closed externally
        (liquidation, manual close), the order is rejected
        by the exchange instead of opening a new position
        in the opposite direction.

    Args:
        symbol       : Trading symbol, e.g. "BTCUSD"
        signal       : Signal string from generate_signals()
        market_price : Current market price (logged only, not used in order)
        size         : Order size in lots from position_sizer.py

    Returns:
        Order dict if an order was placed, None otherwise.
    """
    _validate_symbol(symbol)

    # F3: reduce_only is "true" for exits, "false" for entries
    signal_map = {
        "BUY"      : ("buy",  "false"),   # open long
        "SELL"     : ("sell", "false"),   # open short
        "EXIT_BUY" : ("sell", "true"),    # close long  — reduce_only required
        "EXIT_SELL": ("buy",  "true"),    # close short — reduce_only required
    }

    mapping = signal_map.get(signal)

    if mapping is None:
        logger.debug(f"No actionable signal for {symbol}: '{signal}'")
        return None

    side, reduce_only = mapping

    logger.info(
        f"Executing signal | "
        f"Symbol: {symbol} | "
        f"Signal: {signal} -> Side: {side.upper()} | "
        f"reduce_only: {reduce_only} | "
        f"Price: {market_price} | "
        f"Size: {size}"
    )

    return place_order(symbol, side, size, reduce_only=reduce_only)


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print("\n================================================")
    print(" DEMO EXECUTOR — CONNECTION TEST")
    print("================================================\n")

    # Test 1: Fetch all open positions
    print("[TEST 1] Fetching all open perpetual futures positions...\n")
    try:
        all_positions = get_open_positions()
        print(f"  Total open positions: {len(all_positions)}\n")
    except Exception as e:
        print(f"  ERROR: {e}\n")

    # Test 2: Place a demo BUY market order for BTCUSD
    print("[TEST 2] Placing demo BUY market order for BTCUSD (size=1)...\n")
    try:
        order = place_order("BTCUSD", "buy", size=1, reduce_only="false")
        print(f"  Order ID    : {order.get('id')}")
        print(f"  Symbol      : {order.get('product_symbol')}")
        print(f"  Side        : {order.get('side', '').upper()}")
        print(f"  Size        : {order.get('size')}")
        print(f"  State       : {order.get('state')}")
        print(f"  Created At  : {order.get('created_at')}\n")
    except Exception as e:
        print(f"  ERROR: {e}\n")

    # Test 3: Signal execution mapping
    print("[TEST 3] Testing execute_signal() mapping...\n")
    test_cases = [
        ("ETHUSD",  "BUY"),
        ("SOLUSD",  "SELL"),
        ("BNBUSD",  "EXIT_BUY"),
        ("DOGEUSD", "EXIT_SELL"),
        ("BTCUSD",  None),
    ]
    for sym, sig in test_cases:
        try:
            result = execute_signal(sym, sig, size=1)
            status = f"Order ID {result.get('id')}" if result else "No action"
            print(f"  {sym} | Signal: {str(sig):<12} -> {status}")
        except Exception as e:
            print(f"  {sym} | Signal: {str(sig):<12} -> ERROR: {e}")

    print("\n================================================")
    print(" TEST COMPLETE — Check logs/demo_executor.log")
    print("================================================\n")
