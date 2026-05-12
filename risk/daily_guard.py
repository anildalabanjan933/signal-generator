# ============================================================
# daily_guard.py
# ============================================================
# Tracks daily PnL.
# Blocks new trades if daily loss >= MAX_DAILY_LOSS.
# Resets automatically at midnight UTC.
# ============================================================

from datetime import datetime, timezone

MAX_DAILY_LOSS = 20.0   # USD


class DailyGuard:

    def __init__(self):
        self.daily_pnl   = 0.0
        self.trading_day = self._today()

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check_day_reset(self):
        """Auto-reset at midnight UTC."""
        if self._today() != self.trading_day:
            print(f"[DAILY GUARD] New day detected. Resetting daily PnL.")
            self.daily_pnl   = 0.0
            self.trading_day = self._today()

    def record_pnl(self, amount: float):
        """
        Call this after every trade closes.
        Pass positive value for profit, negative for loss.
        Example: guard.record_pnl(-5.50)
        """
        self._check_day_reset()
        self.daily_pnl += amount
        print(f"[DAILY GUARD] PnL recorded: {amount:+.2f} | Daily total: {self.daily_pnl:.2f}")

    def is_trading_allowed(self) -> bool:
        """
        Returns True if safe to trade.
        Returns False if daily loss limit hit.
        """
        self._check_day_reset()
        if self.daily_pnl <= -MAX_DAILY_LOSS:
            print(f"[DAILY GUARD] Daily loss limit hit ({self.daily_pnl:.2f}). Trading blocked.")
            return False
        return True

    def get_daily_pnl(self) -> float:
        return self.daily_pnl
