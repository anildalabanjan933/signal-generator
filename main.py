# =====================================================
# main.py - Entry point, runs scanner on a timer
# =====================================================

import schedule
import time
from scanner import run_scanner
from strategies.futures_4h_1h.config import SCAN_INTERVAL_SECONDS

print("=" * 55)
print("  SIGNAL GENERATOR STARTED")
print(f"  Scanning every {SCAN_INTERVAL_SECONDS // 60} minutes")
print("  Press Ctrl+C to stop")
print("=" * 55)

# Run immediately on start
run_scanner()

# Then run on schedule
schedule.every(SCAN_INTERVAL_SECONDS).seconds.do(run_scanner)

while True:
    schedule.run_pending()
    time.sleep(1)
