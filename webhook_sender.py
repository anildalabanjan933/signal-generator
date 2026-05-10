# =====================================================
# webhook_sender.py - Send signals to Delta Exchange TradingBot
# =====================================================

import requests
import json
from datetime import datetime
from config import WEBHOOK_URL                          # FIX 4: ALGOTEST_WEBHOOK_URL -> WEBHOOK_URL


def send_signal(symbol: str, signal_data: dict):
    """
    Send BUY/SELL signal to Delta Exchange TradingBot webhook.
    NONE signals are ignored and not sent.
    """

    if signal_data["signal"] == "NONE":
        return

    payload = {
        "symbol"    : symbol,
        "action"    : signal_data["signal"],
        "system"    : signal_data.get("system", ""),
        "price"     : signal_data.get("price", 0),
        "atr"       : signal_data.get("atr", 0),
        "timestamp" : datetime.utcnow().isoformat()
    }

    try:
        response = requests.post(
            WEBHOOK_URL,                               # FIX 4: ALGOTEST_WEBHOOK_URL -> WEBHOOK_URL
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"  [SIGNAL SENT] {symbol} | {payload['action']} | "
              f"{payload['system']} | Price: {payload['price']} | "
              f"Status: {response.status_code}")

    except Exception as e:
        print(f"  [WEBHOOK ERROR] {symbol}: {e}")
