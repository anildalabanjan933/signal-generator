# ============================================================
# position_sizer.py
#
# FIXES APPLIED:
#   F1 - BNBUSD CONTRACT_VALUES corrected from 0.01 to 0.1.
#        Verified from Delta Exchange API (May 2026):
#        BNBUSD contract_value = 0.1 BNB/lot.
#        Previous value 0.01 was 10x understated.
#        This caused position sizing to be 10x too small
#        for all BNBUSD trades.
#   F2 - AVAXUSD removed from CONTRACT_VALUES.
#        AVAXUSD is not in SYMBOLS list in either
#        live_runner. Dead entry removed for consistency.
# ============================================================

from risk.risk_config import TRADE_MARGIN, LEVERAGE


# Contract value per lot — verified from Delta Exchange API (May 2026)
# This is defined here directly so position_sizer works for
# both futures_4h_1h and futures_2h_30m strategies equally.
#
# Delta Exchange API confirmed values:
#   BTCUSD  : 0.001 BTC/lot  (1 lot = 0.001 BTC)
#   ETHUSD  : 0.01  ETH/lot  (1 lot = 0.01  ETH)
#   SOLUSD  : 1.0   SOL/lot  (1 lot = 1     SOL)
#   BNBUSD  : 0.1   BNB/lot  (1 lot = 0.1   BNB)  F1: was 0.01
#   DOGEUSD : 100   DOGE/lot (1 lot = 100   DOGE)
CONTRACT_VALUES = {
    "BTCUSD"  : 0.001,
    "ETHUSD"  : 0.01,
    "SOLUSD"  : 1.0,
    "BNBUSD"  : 0.1,    # F1: corrected from 0.01 to 0.1
    "DOGEUSD" : 100.0,  # F2: AVAXUSD removed — not in SYMBOLS list
}


def calculate_position_size(symbol: str, price: float) -> int:
    """
    Calculate correct lot size for a given symbol and price.

    Formula:
        target_notional = TRADE_MARGIN * LEVERAGE
        lots = target_notional / (contract_value * price)

    Args:
        symbol : Trading symbol e.g. "BTCUSD", "DOGEUSD"
        price  : Current market price of the symbol

    Returns:
        Integer lot size (minimum 1)

    Raises:
        ValueError if symbol not found in CONTRACT_VALUES
        ValueError if price is zero or negative
    """

    if price <= 0:
        raise ValueError(f"Invalid price {price} for {symbol}")

    contract_value = CONTRACT_VALUES.get(symbol)
    if contract_value is None:
        raise ValueError(
            f"Symbol '{symbol}' not found in CONTRACT_VALUES. "
            f"Add it to risk/position_sizer.py before trading."
        )

    target_notional = TRADE_MARGIN * LEVERAGE  # e.g. 15 * 20 = $300

    lots = target_notional / (contract_value * price)

    return max(1, int(round(lots)))
