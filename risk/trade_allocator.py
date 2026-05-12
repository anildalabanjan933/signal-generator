# ============================================================
# trade_allocator.py
# ============================================================
# Tracks how many trades are currently open.
# Blocks new trades if active trades >= MAX_OPEN_TRADES.
# ============================================================

MAX_OPEN_TRADES = 5


class TradeAllocator:

    def __init__(self):
        self.active_trades = {}   # symbol -> True

    def can_open_trade(self) -> bool:
        """
        Returns True if a new trade slot is available.
        Returns False if already at max open trades.
        """
        count = len(self.active_trades)
        if count >= MAX_OPEN_TRADES:
            print(f"[ALLOCATOR] Max trades reached ({count}/{MAX_OPEN_TRADES}). Rejecting new trade.")
            return False
        print(f"[ALLOCATOR] Trade slot available ({count}/{MAX_OPEN_TRADES}).")
        return True

    def register_trade(self, symbol: str):
        """Call this immediately after an order is placed."""
        self.active_trades[symbol] = True
        print(f"[ALLOCATOR] Trade registered: {symbol} | Open: {len(self.active_trades)}/{MAX_OPEN_TRADES}")

    def close_trade(self, symbol: str):
        """Call this when a position is closed."""
        if symbol in self.active_trades:
            del self.active_trades[symbol]
            print(f"[ALLOCATOR] Trade closed: {symbol} | Open: {len(self.active_trades)}/{MAX_OPEN_TRADES}")

    def is_symbol_active(self, symbol: str) -> bool:
        """Returns True if this symbol already has an open trade."""
        return symbol in self.active_trades

    def get_active_count(self) -> int:
        return len(self.active_trades)

    def get_active_trades(self) -> list:
        return list(self.active_trades.keys())
