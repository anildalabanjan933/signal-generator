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
# =====================================================

import logging

log = logging.getLogger(__name__)


def run_scanner():
    """
    Coordinator that runs both strategy live runners.
    Each live_runner handles its own:
      - candle fetch
      - indicator calculation
      - trend alignment
      - signal generation
      - risk checks (DailyGuard + TradeAllocator)
      - order execution
      - CSV logging
    """

    log.info("=" * 55)
    log.info("  SIGNAL SCANNER RUNNING")
    log.info("=" * 55)

    # ── Strategy 1: futures_4h_1h ─────────────────────────
    try:
        log.info("Running strategy: futures_4h_1h")
        from strategies.futures_4h_1h.live_runner import run_once as run_4h_1h
        run_4h_1h()
    except Exception as e:
        log.error(f"futures_4h_1h failed: {e}", exc_info=True)

    # ── Strategy 2: futures_2h_30m ────────────────────────
    try:
        log.info("Running strategy: futures_2h_30m")
        from strategies.futures_2h_30m.live_runner import run_once as run_2h_30m
        run_2h_30m()
    except Exception as e:
        log.error(f"futures_2h_30m failed: {e}", exc_info=True)

    log.info("=" * 55)
    log.info("  SCAN COMPLETE")
    log.info("=" * 55)
