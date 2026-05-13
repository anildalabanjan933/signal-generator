# =====================================================
# main.py - Entry point, runs both strategy scanners
#           on a timer
#
# FIXES APPLIED:
#   F1 - Removed "from config import SCAN_INTERVAL_SECONDS"
#        There is no root-level config.py. Each strategy
#        has its own config. Interval is defined here directly.
#   F2 - Added error handling around run_scanner() so a
#        single crash does not kill the entire bot.
#   F3 - Added basic file logging so Railway log history
#        is not the only record of what happened.
#   F4 - SCAN_INTERVAL_SECONDS defined locally here.
#        Set to 3600 (1 hour) — aligned to the slowest
#        trigger timeframe (1H in futures_4h_1h).
#        futures_2h_30m triggers on 30m but scanning
#        every 60 min is safe for swing entries.
#        Reduce to 1800 if you want 30m alignment.
# =====================================================

import schedule
import time
import logging
import os
from datetime import datetime, timezone

# ── Logging setup ─────────────────────────────────────────
LOG_DIR  = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [
        logging.FileHandler(os.path.join(LOG_DIR, "main.log")),
        logging.StreamHandler()   # also prints to Railway console
    ]
)

log = logging.getLogger(__name__)

# ── Scan interval ─────────────────────────────────────────
# F4: Defined here directly — no root config.py exists.
# 3600 = 1 hour, aligned to 1H trigger TF (futures_4h_1h).
# Change to 1800 for 30m alignment (futures_2h_30m).
SCAN_INTERVAL_SECONDS = 3600

# ── Import scanner ────────────────────────────────────────
from scanner import run_scanner

# ── Safe wrapper ──────────────────────────────────────────
def safe_run_scanner():
    """
    Wraps run_scanner() in try/except so a single scan
    failure does not crash the entire bot and stop
    all future scheduled scans.
    """
    try:
        log.info("Scan cycle starting...")
        run_scanner()
        log.info("Scan cycle complete.")
    except Exception as e:
        log.error(f"Scan cycle failed: {e}", exc_info=True)

# ── Startup ───────────────────────────────────────────────
log.info("=" * 55)
log.info("  SIGNAL GENERATOR STARTED")
log.info(f"  Scanning every {SCAN_INTERVAL_SECONDS // 60} minutes")
log.info(f"  Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
log.info("=" * 55)

# Run immediately on start
safe_run_scanner()

# Then run on schedule
schedule.every(SCAN_INTERVAL_SECONDS).seconds.do(safe_run_scanner)

while True:
    schedule.run_pending()
    time.sleep(1)
