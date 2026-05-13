# ============================================================
# demo_trader.py - Demo account trade execution
#
# FIXES APPLIED:
#   F1 - BNBUSD CONTRACT_VALUES corrected from 0.01 to 0.1.
#        Verified from Delta Exchange API (May 2026).
#        Was 10x understated causing wrong position sizing.
#   F2 - Misleading exit comments corrected.
#        EXIT_BUY closes a long: place SELL reduce_only=True.
#        EXIT_SELL closes a short: place BUY reduce_only=True.
#        Logic was already correct, comments were wrong.
#   F3 - Added KeyError guard on PRODUCT_IDS lookup.
#        Missing symbol now raises ValueError immediately
#        instead of silently failing inside the API call.
# ============================================================

import os
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
sys.path.insert(0, PROJECT_ROOT)

from execution.delta_api import DeltaAPI
from risk.position_sizer import calculate_position_size

# ── API client ────────────────────────────────────────────
api = DeltaAPI(
    api_key    = os.environ.get("DELTA_API_KEY", ""),
    api_secret = os.environ.get("DELTA_API_SECRET", ""),
)

# ── Product IDs (Delta Exchange perpetual futures) ────────
# Verify at: https://api.india.delta.exchange/v2/products
PRODUCT_IDS = {
    "BTCUSD"  : 139,
    "ETHUSD"  : 1699,
    "SOLUSD"  : 92572,
    "BNBUSD"  : 15042,
    "DOGEUSD" : 196,
}

# ── Contract values per lot — verified from Delta Exchange API (May 2026)
# F1: BNBUSD corrected from 0.01 to 0.1
CONTRACT_VALUES = {
    "BTCUSD"  : 0.001,
    "ETHUSD"  : 0.01,
    "SOLUSD"  : 1.0,
    "BNBUSD"  : 0.1,    # F1: was 0.01, corrected to 0.1
    "DOGEUSD" : 100.0,
}


def execute_signal(symbol: str, signal: str, price: float) -> dict:
    """
    Execute a trade signal on the Delta Exchange demo account.

    Args:
        symbol : e.g. "BTCUSD"
        signal : "BUY", "SELL", "EXIT_BUY", "EXIT_SELL"
        price  : current market price for lot size calculation

    Returns:
        API response dict

    Raises:
        ValueError if symbol not in PRODUCT_IDS
    """

    # F3: Guard on missing symbol
    if symbol not in PRODUCT_IDS:
        raise ValueError(
            f"Symbol '{symbol}' not found in PRODUCT_IDS. "
            f"Available: {list(PRODUCT_IDS.keys())}"
        )

    product_id = PRODUCT_IDS[symbol]
    lots       = calculate_position_size(symbol, price)

    if signal == "BUY":
        # Open long position
        return api.place_order(
            product_id = product_id,
            side       = "buy",
            size       = lots,
            order_type = "market_order",
            reduce_only = "false",
        )

    elif signal == "SELL":
        # Open short position
        return api.place_order(
            product_id = product_id,
            side       = "sell",
            size       = lots,
            order_type = "market_order",
            reduce_only = "false",
        )

    elif signal == "EXIT_BUY":
        # F2: Close long position — place SELL with reduce_only=True
        # reduce_only ensures this cannot open a new short if
        # the long was already closed externally
        return api.place_order(
            product_id = product_id,
            side       = "sell",
            size       = lots,
            order_type = "market_order",
            reduce_only = "true",
        )

    elif signal == "EXIT_SELL":
        # F2: Close short position — place BUY with reduce_only=True
        return api.place_order(
            product_id = product_id,
            side       = "buy",
            size       = lots,
            order_type = "market_order",
            reduce_only = "true",
        )

    else:
        raise ValueError(f"Unknown signal '{signal}' for {symbol}")
