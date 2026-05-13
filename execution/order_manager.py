# ============================================================
# order_manager.py - Order and position management
#
# FIXES APPLIED:
#   F1 - BNBUSD CONTRACT_VALUES corrected from 0.01 to 0.1.
#        Verified from Delta Exchange API (May 2026).
#   F2 - calculate_lots() removed. Replaced with direct call
#        to position_sizer.calculate_position_size().
#        Two sources of truth for the same calculation caused
#        drift risk when one file is updated and the other is not.
#   F3 - close_position() now uses reduce_only="true".
#        Without reduce_only, if the position was already closed
#        externally (liquidation, manual close), the order would
#        open a new position in the opposite direction.
#        reduce_only prevents this — order is rejected if no
#        position exists to close.
#   F4 - get_open_position() now raises on API error.
#        Previously returned None on both "no position" and
#        "API call failed". Caller could not distinguish the two.
#        Now raises RuntimeError on API failure.
#        Returns None only when position genuinely does not exist.
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

# ── Product IDs ───────────────────────────────────────────
PRODUCT_IDS = {
    "BTCUSD"  : 139,
    "ETHUSD"  : 1699,
    "SOLUSD"  : 92572,
    "BNBUSD"  : 15042,
    "DOGEUSD" : 196,
}

# ── Contract values — verified from Delta Exchange API (May 2026)
# F1: BNBUSD corrected from 0.01 to 0.1
CONTRACT_VALUES = {
    "BTCUSD"  : 0.001,
    "ETHUSD"  : 0.01,
    "SOLUSD"  : 1.0,
    "BNBUSD"  : 0.1,    # F1: was 0.01, corrected to 0.1
    "DOGEUSD" : 100.0,
}


def open_position(symbol: str, side: str, price: float) -> dict:
    """
    Open a new position.

    Args:
        symbol : e.g. "BTCUSD"
        side   : "buy" or "sell"
        price  : current market price for lot size calculation

    Returns:
        API response dict
    """
    if symbol not in PRODUCT_IDS:
        raise ValueError(f"Symbol '{symbol}' not in PRODUCT_IDS")

    # F2: Use position_sizer directly — single source of truth
    lots = calculate_position_size(symbol, price)

    return api.place_order(
        product_id = PRODUCT_IDS[symbol],
        side       = side,
        size       = lots,
        order_type = "market_order",
        reduce_only = "false",
    )


def close_position(symbol: str, side: str, price: float) -> dict:
    """
    Close an existing position.

    Args:
        symbol : e.g. "BTCUSD"
        side   : "sell" to close long, "buy" to close short
        price  : current market price for lot size calculation

    Returns:
        API response dict

    Notes:
        F3: reduce_only="true" is mandatory here.
        If the position was already closed externally
        (liquidation, manual close), reduce_only causes
        the order to be rejected rather than opening a
        new position in the opposite direction.
    """
    if symbol not in PRODUCT_IDS:
        raise ValueError(f"Symbol '{symbol}' not in PRODUCT_IDS")

    lots = calculate_position_size(symbol, price)

    return api.place_order(
        product_id  = PRODUCT_IDS[symbol],
        side        = side,
        size        = lots,
        order_type  = "market_order",
        reduce_only = "true",   # F3: prevents accidental position flip
    )


def get_open_position(symbol: str) -> dict | None:
    """
    Fetch current open position for a symbol.

    Returns:
        Position dict if open position exists.
        None if no position exists for this symbol.

    Raises:
        RuntimeError if the API call itself fails.
        F4: Distinguishes API failure from "no position".
    """
    if symbol not in PRODUCT_IDS:
        raise ValueError(f"Symbol '{symbol}' not in PRODUCT_IDS")

    response = api.get_position(product_id=PRODUCT_IDS[symbol])

    # F4: Raise on API error — do not silently return None
    if not response.get("success"):
        raise RuntimeError(
            f"get_open_position API call failed for {symbol}: "
            f"{response.get('error', 'unknown error')}"
        )

    result = response.get("result")

    # A position with size=0 means no open position
    if result is None or result.get("size", 0) == 0:
        return None

    return result


def cancel_all_orders(symbol: str) -> dict:
    """
    Cancel all open orders for a symbol.

    Returns:
        API response dict
    """
    if symbol not in PRODUCT_IDS:
        raise ValueError(f"Symbol '{symbol}' not in PRODUCT_IDS")

    return api.cancel_all_orders(product_id=PRODUCT_IDS[symbol])
