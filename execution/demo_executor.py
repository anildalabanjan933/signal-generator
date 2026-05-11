# ============================================================
# execution/demo_executor.py
#
# Delta Exchange DEMO (Testnet) Executor
# Connects to: https://cdn-ind.testnet.deltaex.org
#
# Supports : BTCUSD, ETHUSD, SOLUSD, BNBUSD, DOGEUSD
# Orders   : Market orders only
# Account  : DEMO / Testnet only — no live funds
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
# LOG DIRECTORY — ensure it exists before logging starts
# ============================================================

os.makedirs("execution", exist_ok=True)

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("execution/demo_executor.log"),
    ],
)

logger = logging.getLogger("DemoExecutor")

# ============================================================
# CONFIG
# ============================================================

# Demo / Testnet base URL — never points to live account
DEMO_BASE_URL = "https://cdn-ind.testnet.deltaex.org"

# Load credentials from environment variables.
# Set these in your .env file or system environment.
# Never hardcode credentials in source code.
DEMO_API_KEY    = os.environ.get("DEMO_API_KEY", "fiJcWSJJKWuwo2RnISHZpDwgEg8QHE")
DEMO_API_SECRET = os.environ.get("DEMO_API_SECRET", "K4Iwq6QPD9hdJnFJRbygo52ALDmhamxnrVCSPXHCdrB1gAEN18v7D7XoPOJZ")

# Supported symbols and their default order sizes (in lots/contracts)
# Adjust sizes to match your risk parameters.
SYMBOL_CONFIG = {
    "BTCUSD" : {"size": 1},
    "ETHUSD" : {"size": 1},
    "SOLUSD" : {"size": 1},
    "BNBUSD" : {"size": 1},
    "DOGEUSD": {"size": 1},
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
    """
    return hmac.new(
        bytes(secret, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_headers(method: str, path: str, query_string: str = "", body: str = "") -> dict:
    """
    Build authenticated request headers.

    Required headers for all authenticated Delta Exchange requests:
        api-key      : Your API key
        timestamp    : Current unix timestamp (seconds)
        signature    : HMAC-SHA256 of (method + timestamp + path + query_string + body)
        User-Agent   : Client identifier
        Content-Type : application/json
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

def _request(method: str, path: str, params: dict = None, body: dict = None) -> dict:
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
    """
    url          = f"{DEMO_BASE_URL}{path}"
    query_string = ""
    body_str     = ""

    # Build query string for signature (must match exact URL encoding)
    if params:
        query_string = "?" + "&".join(f"{k}={v}" for k, v in params.items())

    # Serialize body for signature — compact JSON, no spaces
    if body:
        body_str = json.dumps(body, separators=(",", ":"))

    headers = _build_headers(method, path, query_string, body_str)

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            data=body_str if body else None,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("success"):
            error_detail = result.get("error", result)
            raise ValueError(f"API error on {method} {path}: {error_detail}")

        return result

    # FIX: Timeout must be caught BEFORE ConnectionError
    # because Timeout is a subclass of ConnectionError.
    # Previous order made the Timeout handler unreachable.
    except requests.exceptions.Timeout as e:
        raise ConnectionError(f"Request timed out for {method} {path}: {e}")

    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(f"Network connection failed for {method} {path}: {e}")

    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP error {response.status_code} for {method} {path}: {e}")

    except ValueError:
        raise  # re-raise API-level errors as-is

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

def place_order(symbol: str, side: str, size: Optional[int] = None) -> dict:
    """
    Place a market order on the Delta Exchange Demo account.

    Args:
        symbol : Trading symbol, e.g. "BTCUSD"
        side   : "buy" or "sell"
        size   : Order size in lots/contracts.
                 If None, uses the default size from SYMBOL_CONFIG.

    Returns:
        Order response dict from the API containing:
            id             : Order ID
            product_symbol : Symbol
            side           : buy/sell
            size           : Order size
            order_type     : market_order
            state          : open/pending/closed/cancelled
            created_at     : Timestamp in microseconds

    Raises:
        ValueError      : Invalid symbol or side
        ConnectionError : Network failure
        RuntimeError    : API or unexpected error
    """
    _validate_symbol(symbol)

    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"Invalid side '{side}'. Must be 'buy' or 'sell'.")

    # Use default size if not provided
    order_size = size if size is not None else SYMBOL_CONFIG[symbol]["size"]

    if order_size <= 0:
        raise ValueError(f"Order size must be a positive integer. Got: {order_size}")

    path = "/v2/orders"
    body = {
        "product_symbol": symbol,
        "side"          : side,
        "size"          : order_size,
        "order_type"    : "market_order",
    }

    logger.info(
        f"Placing DEMO market order | Symbol: {symbol} | Side: {side.upper()} | Size: {order_size}"
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

    Uses GET /v2/positions/margined which returns all open positions.
    Optionally filters by symbol if provided.

    Args:
        symbol : Optional. Filter results to a specific symbol, e.g. "BTCUSD".
                 If None, returns all open perpetual futures positions.

    Returns:
        List of position dicts, each containing:
            product_symbol    : Symbol
            size              : Position size (positive=long, negative=short)
            entry_price       : Average entry price
            margin            : Margin allocated
            liquidation_price : Liquidation price
            realized_pnl      : Realized PnL since position opened
            realized_funding  : Realized funding since position opened

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

        # Filter by symbol if requested
        if symbol:
            positions = [p for p in positions if p.get("product_symbol") == symbol]

        # Log each open position
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
# CONVENIENCE: EXECUTE SIGNAL
# ============================================================

def execute_signal(symbol: str, signal: str, size: Optional[int] = None) -> Optional[dict]:
    """
    Translate a strategy signal into a demo market order.

    This is the primary integration point for live_runner.py.

    Signal mapping:
        "BUY"        -> place_order(symbol, "buy",  size)
        "SELL"       -> place_order(symbol, "sell", size)
        "EXIT_BUY"   -> place_order(symbol, "sell", size)  [close long]
        "EXIT_SELL"  -> place_order(symbol, "buy",  size)  [close short]
        None / other -> no action

    Args:
        symbol : Trading symbol, e.g. "BTCUSD"
        signal : Signal string from generate_signals()
        size   : Optional order size override

    Returns:
        Order dict if an order was placed, None otherwise
    """
    _validate_symbol(symbol)

    signal_map = {
        "BUY"      : "buy",
        "SELL"     : "sell",
        "EXIT_BUY" : "sell",   # exit long = sell
        "EXIT_SELL": "buy",    # exit short = buy
    }

    side = signal_map.get(signal)

    if side is None:
        logger.debug(f"No actionable signal for {symbol}: '{signal}'")
        return None

    logger.info(f"Executing signal | Symbol: {symbol} | Signal: {signal} -> Side: {side.upper()}")

    return place_order(symbol, side, size)


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print("\n================================================")
    print(" DEMO EXECUTOR — CONNECTION TEST")
    print("================================================\n")

    # Test 1: Fetch open positions for all supported symbols
    print("[TEST 1] Fetching all open perpetual futures positions...\n")
    try:
        all_positions = get_open_positions()
        print(f"  Total open positions: {len(all_positions)}\n")
    except Exception as e:
        print(f"  ERROR: {e}\n")

    # Test 2: Place a demo BUY market order for BTCUSD
    print("[TEST 2] Placing demo BUY market order for BTCUSD (size=1)...\n")
    try:
        order = place_order("BTCUSD", "buy", size=1)
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
    print(" TEST COMPLETE — Check demo_executor.log for details")
    print("================================================\n")
if __name__ == "__main__":

    import json

    # ── Build payload ────────────────────────────────────────
    order_payload = {
        "product_symbol": "BTCUSD",
        "side"          : "buy",
        "size"          : 1,
        "order_type"    : "market_order",
    }

    body_str = json.dumps(order_payload, separators=(",", ":"))

    method       = "POST"
    path         = "/v2/orders"
    query_string = ""
    timestamp    = str(int(time.time()))

    signature_data = method + timestamp + path + query_string + body_str
    signature      = _generate_signature(DEMO_API_SECRET, signature_data)

    headers = {
        "api-key"     : DEMO_API_KEY,
        "timestamp"   : timestamp,
        "signature"   : signature,
        "User-Agent"  : "python-demo-executor",
        "Content-Type": "application/json",
    }

    print("\n--- DEBUG REQUEST ---")
    print(f"URL     : {DEMO_BASE_URL}{path}")
    print(f"Headers : {headers}")
    print(f"Body    : {body_str}")
    print(f"Sig data: {signature_data}")

    response = requests.post(
        f"{DEMO_BASE_URL}{path}",
        headers=headers,
        data=body_str,
        timeout=(3, 27)
    )

    print(f"\n--- DEBUG RESPONSE ---")
    print(f"Status  : {response.status_code}")
    print(f"Body    : {response.text}")   # raw response — shows exact API error
