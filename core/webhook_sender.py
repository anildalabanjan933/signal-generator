import requests

from strategies.futures_4h_1h.config import *

# =====================================================
# BTC LONG ENTRY
# =====================================================

def send_btc_long_entry():

    response = requests.post(
        BTC_LONG_ENTRY_WEBHOOK,
        json=BTC_LONG_ENTRY_PAYLOAD,
        timeout=10
    )

    print("BTC LONG ENTRY:", response.status_code)
    print(response.text)


# =====================================================
# BTC LONG EXIT
# =====================================================

def send_btc_long_exit():

    response = requests.post(
        BTC_LONG_EXIT_WEBHOOK,
        json=BTC_LONG_EXIT_PAYLOAD,
        timeout=10
    )

    print("BTC LONG EXIT:", response.status_code)
    print(response.text)


# =====================================================
# BTC SHORT ENTRY
# =====================================================

def send_btc_short_entry():

    response = requests.post(
        BTC_SHORT_ENTRY_WEBHOOK,
        json=BTC_SHORT_ENTRY_PAYLOAD,
        timeout=10
    )

    print("BTC SHORT ENTRY:", response.status_code)
    print(response.text)


# =====================================================
# BTC SHORT EXIT
# =====================================================

def send_btc_short_exit():

    response = requests.post(
        BTC_SHORT_EXIT_WEBHOOK,
        json=BTC_SHORT_EXIT_PAYLOAD,
        timeout=10
    )

    print("BTC SHORT EXIT:", response.status_code)
    print(response.text)