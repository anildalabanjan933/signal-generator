# ============================================================
# execution/demo_executor.py
# ============================================================

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

import requests
from dotenv import load_dotenv

from risk.position_sizer import calculate_position_size

# Load .env variables
load_dotenv()

# ============================================================
# LOG DIRECTORY
# ============================================================

os.makedirs("execution", exist_ok=True)

# ============================================================
# LOGGING
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

DEMO_BASE_URL = "https://cdn-ind.testnet.deltaex.org"

# Load API keys ONLY from .env
DEMO_API_KEY = os.environ.get("DEMO_API_KEY")
DEMO_API_SECRET = os.environ.get("DEMO_API_SECRET")

if not DEMO_API_KEY or not DEMO_API_SECRET:
    raise EnvironmentError(
        "DEMO_API_KEY and DEMO_API_SECRET must be set in .env file"
    )

REQUEST_TIMEOUT = (3, 27)

# ============================================================
# AUTH
# ============================================================

def _generate_signature(secret: str, message: str) -> str:
    return hmac.new(
        bytes(secret, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_headers(
    method: str,
    path: str,
    query_string: str = "",
    body: str = ""
) -> dict:

    timestamp = str(int(time.time()))

    signature_data = (
        method +
        timestamp +
        path +
        query_string +
        body
    )

    signature = _generate_signature(
        DEMO_API_SECRET,
        signature_data
    )

    return {
        "api-key": DEMO_API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "User-Agent": "python-demo-executor",
        "Content-Type": "application/json",
    }

# ============================================================
# HTTP REQUEST
# ============================================================

def _request(
    method: str,
    path: str,
    params: dict = None,
    body: dict = None
) -> dict:

    url = f"{DEMO_BASE_URL}{path}"

    query_string = ""
    body_str = ""

    if params:
        query_string = "?" + "&".join(
            f"{k}={v}" for k, v in params.items()
        )

    if body:
        body_str = json.dumps(body, separators=(",", ":"))

    headers = _build_headers(
        method,
        path,
        query_string,
        body_str
    )

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
            raise ValueError(result)

        return result

    except requests.exceptions.Timeout as e:
        raise ConnectionError(f"Timeout: {e}")

    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(f"Connection failed: {e}")

    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"HTTP error: {e}")

# ============================================================
# PLACE ORDER
# ============================================================

def place_order(
    symbol: str,
    side: str,
    market_price: float,
    size: Optional[float] = None
) -> dict:

    side = side.lower()

    if side not in ("buy", "sell"):
        raise ValueError("Side must be buy or sell")

    # ------------------------------------------------
    # AUTO POSITION SIZING
    # ------------------------------------------------

    if size is None:
        order_size = calculate_position_size(market_price)
    else:
        order_size = size

    path = "/v2/orders"

    body = {
        "product_symbol": symbol,
        "side": side,
        "size": order_size,
        "order_type": "market_order",
    }

    logger.info(
        f"Placing order | "
        f"{symbol} | "
        f"{side.upper()} | "
        f"Size={order_size}"
    )

    response = _request(
        "POST",
        path,
        body=body
    )

    return response.get("result", {})

# ============================================================
# EXECUTE SIGNAL
# ============================================================

def execute_signal(
    symbol: str,
    signal: str,
    market_price: float,
    size: Optional[float] = None
):

    signal_map = {
        "BUY": "buy",
        "SELL": "sell",
        "EXIT_BUY": "sell",
        "EXIT_SELL": "buy",
    }

    side = signal_map.get(signal)

    if side is None:
        return None

    logger.info(
        f"Executing signal | "
        f"{symbol} | "
        f"{signal}"
    )

    return place_order(
        symbol=symbol,
        side=side,
        market_price=market_price,
        size=size
    )

# ============================================================
# GET OPEN POSITIONS
# ============================================================

def get_open_positions(symbol: str = None):

    path = "/v2/positions/margined"

    params = {
        "contract_types": "perpetual_futures"
    }

    response = _request(
        "GET",
        path,
        params=params
    )

    positions = response.get("result", [])

    if symbol:
        positions = [
            p for p in positions
            if p.get("product_symbol") == symbol
        ]

    return positions

# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("\n================================================")
    print(" DEMO EXECUTOR TEST ")
    print("================================================\n")

    try:

        positions = get_open_positions()

        print(f"Open positions: {len(positions)}")

        btc_price = 80000

        order = execute_signal(
            symbol="BTCUSD",
            signal="BUY",
            market_price=btc_price
        )

        print("Test order successful")
        print(order)

    except Exception as e:

        print(f"ERROR: {e}")