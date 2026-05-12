# ============================================================
# position_sizer.py
# ============================================================

from risk.risk_config import TRADE_MARGIN, LEVERAGE

def calculate_position_size(price: float) -> int:

    position_value = TRADE_MARGIN * LEVERAGE

    size = position_value / price

    if size <= 0:
        return 1

    return max(1, round(size, 6))