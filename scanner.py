# =====================================================
# scanner.py - Multi-strategy coordinator
#
# FIXES APPLIED:
#   F1 - Removed "from config import ..." — no root
#        config.py exists. Each strategy has its own.
#   F2 - Removed duplicate build_params() — already
#        defined in each strategy's config.py.
#   F3 - Removed broken imports: signal_engine and
#        data_fetcher do not exist in the file tree.
#   F4 - scanner.py now calls each strategy's
#        live_runner directly. Signal logic, candle
#        fetch, indicator calc, and trend alignment
#        all live inside the live_runners already.
#        No duplication needed here.
#   F5 - Added per-strategy error handling so one
#        strategy crash does not stop the other.
#   F6 - futures_2h_30m strategy added. Was missing
#        entirely from the original scanner.
#   F7 - Candle fetch reduced to last N candles only
#        (handled inside each live_runner). Fetching
#        730 days on every scan cycle is too slow.
#
# FIX THIS SESSION:
#   F8 - Strategy imports moved to MODULE LEVEL.
#        Previously imports were inside run_scanner()
#        function body. Python re-imports a module
#        every time the import statement is executed
#        inside a function IF the module is not yet
#        cached in sys.modules. On Railway, if the
#        process restarts or modules are reloaded,
#        this caused guard and allocator instances
#        in each live_runner to reset to zero on
#        every scan cycle. BTCUSD could open 3 times
#        because allocator.active_trades was always
#        empty at the start of each run_scanner() call.
#        Fix: import both live_runners once at module
#        level so their module-level guard and allocator
#        instances are created exactly once and persist
#        for the entire process lifetime.
#
#   F9 - Shared DailyGuard and TradeAllocator instances
#        created here in scanner.py and injected into
#        both live_runners via run_once(guard, allocator).
#        Previously each live_runner had its own separate
#        instances. Two separate allocators meant:
#          - Strategy 1 opened BTCUSD → registered in A
#          - Strategy 2 checked allocator B → empty
#          - Strategy 2 opened BTCUSD again → duplicate
#        Fix: one shared allocator and one shared guard
#        passed into both run_once() calls so both
#        strategies see the same state at all times.
#
#   F10 - GAP 4 FIX: Startup position reconciliation.
#         On every process start (including Railway
#         auto-restarts), shared_allocator starts empty.
#         If the bot restarts mid-trade, it does not know
#         about existing open positions on the exchange.
#         The next scan cycle sees an empty allocator and
#         opens the same symbol again — doubling exposure.
#
#         Fix: _reconcile_open_positions() is called once
#         at module load time (after shared_allocator is
#         created). It calls GET /v2/positions/margined,
#         reads all currently open perpetual futures
#         positions, and calls register_trade(symbol) for
#         each open symbol before the first scan runs.
#
#         This means:
#           - Bot restarts mid-trade on BTCUSD
#           - Reconciliation finds BTCUSD already open
#           - Calls register_trade("BTCUSD") on allocator
#           - First scan sees BTCUSD as already allocated
#           - Does NOT open a second BTCUSD position
#
#         If the API call fails at startup (network issue),
#         the error is logged as WARNING and the bot
#         continues. Allocator starts empty in that case —
#         same behaviour as before this fix. Operator is
#         warned via log so they can investigate.
# =====================================================

import logging

from risk.daily_guard import DailyGuard
from risk.trade_allocator import TradeAllocator
from execution.demo_executor import get_open_positions

import strategies.futures_4h_1h.live_runner as runner_4h_1h
import strategies.futures_2h_30m.live_runner as runner_2h_30m

# ============================================================
# F9: ONE SHARED INSTANCE FOR BOTH STRATEGIES
# Created once when scanner.py is first imported.
# Persists for the entire process lifetime.
# Both strategies read and write the same state.
# ============================================================
shared_guard     = DailyGuard()
shared_allocator = TradeAllocator()

log = logging.getLogger(__name__)


# ============================================================
# F10: GAP 4 — STARTUP POSITION RECONCILIATION
# ============================================================

def _reconcile_open_positions() -> None:
    """
    On startup, fetch all open positions from the exchange
    and pre-fill shared_allocator via register_trade() so
    the bot does not open duplicate positions after a restart.

    Called once at module load time — before the first
    run_scanner() call.

    If the API call fails at startup, the error is logged
    as WARNING and the bot continues with an empty allocator.
    This is the same behaviour as before this fix was added.
    A warning is logged so the operator is aware.
    """
    log.info("Startup reconciliation: checking for existing open positions...")

    try:
        open_positions = get_open_positions()

        if not open_positions:
            log.info(
                "Startup reconciliation: no open positions found. "
                "Allocator starts clean."
            )
            return

        reconciled = []

        for pos in open_positions:
            symbol = pos.get("product_symbol")
            size   = pos.get("size", 0)

            # Only register positions with a non-zero size.
            # size > 0 = long, size < 0 = short, size = 0 = flat.
            if symbol and size != 0:
                shared_allocator.register_trade(symbol)
                reconciled.append(symbol)
                log.info(
                    f"Startup reconciliation: registered existing position | "
                    f"Symbol: {symbol} | Size: {size}"
                )

        if reconciled:
            log.info(
                f"Startup reconciliation complete. "
                f"Pre-filled allocator with: {reconciled} | "
                f"Active count: {shared_allocator.get_active_count()}"
                f"/{shared_allocator.active_trades}"
            )
        else:
            log.info(
                "Startup reconciliation: positions returned but none "
                "with non-zero size. Allocator starts clean."
            )

    except Exception as e:
        log.warning(
            f"Startup reconciliation FAILED — allocator starts empty. "
            f"Risk of duplicate positions if bot restarted mid-trade. "
            f"Error: {e}"
        )


# ============================================================
# F10: Run reconciliation once at module load time.
# Executes before the first run_scanner() call.
# ============================================================
_reconcile_open_positions()


# ============================================================
# SCANNER
# ============================================================

def run_scanner():
    """
    Coordinator that runs both strategy live runners.

    Both strategies share the same DailyGuard and
    TradeAllocator so risk limits are enforced globally
    across all symbols and both strategies combined.

    Each live_runner handles its own:
      - candle fetch
      - indicator calculation
      - trend alignment
      - signal generation
      - order execution
      - CSV logging

    Risk state (open trades, daily loss) is shared
    and passed in via shared_guard and shared_allocator.
    """

    log.info("=" * 55)
    log.info("  SIGNAL SCANNER RUNNING")
    log.info("=" * 55)

    # ── Strategy 1: futures_4h_1h ─────────────────────────
    try:
        log.info("Running strategy: futures_4h_1h")
        runner_4h_1h.run_once(shared_guard, shared_allocator)
    except Exception as e:
        log.error(f"futures_4h_1h failed: {e}", exc_info=True)

    # ── Strategy 2: futures_2h_30m ────────────────────────
    try:
        log.info("Running strategy: futures_2h_30m")
        runner_2h_30m.run_once(shared_guard, shared_allocator)
    except Exception as e:
        log.error(f"futures_2h_30m failed: {e}", exc_info=True)

    log.info("=" * 55)
    log.info("  SCAN COMPLETE")
    log.info("=" * 55)
