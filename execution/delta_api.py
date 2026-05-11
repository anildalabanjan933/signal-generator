import hashlib
import hmac
import time
import requests
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")
BASE_URL = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")

def generate_signature(secret, method, path, query_string, payload, timestamp):
    """Generate HMAC SHA256 signature for Delta Exchange API"""
    message = method + timestamp + path + query_string + payload
    secret_bytes = bytes(secret, 'utf-8')
    message_bytes = bytes(message, 'utf-8')
    signature = hmac.new(secret_bytes, message_bytes, hashlib.sha256)
    return signature.hexdigest()


def get_headers(method, path, query_string="", payload=""):
    """Build authenticated request headers"""
    timestamp = str(int(time.time()))
    signature = generate_signature(API_SECRET, method, path, query_string, payload, timestamp)
    return {
        "api-key": API_KEY,
        "timestamp": timestamp,
        "signature": signature,
        "User-Agent": "python-rest-client",
        "Content-Type": "application/json"
    }


def get_wallet_balance():
    """Fetch wallet balance from Delta Exchange testnet"""
    method = "GET"
    path = "/v2/wallet/balances"
    query_string = ""
    payload = ""

    url = BASE_URL + path
    headers = get_headers(method, path, query_string, payload)

    try:
        response = requests.get(url, headers=headers, timeout=(3, 27))
        data = response.json()

        if response.status_code == 200 and data.get("success"):
            print("Connection Successful!")
            print("Wallet Balances:")
            print("-" * 40)
            for balance in data.get("result", []):
                asset = balance.get("asset", {}).get("symbol", "N/A")
                available = balance.get("available_balance", "0")
                total = balance.get("balance", "0")
                if float(total) > 0:
                    print(f"  Asset   : {asset}")
                    print(f"  Available: {available}")
                    print(f"  Total    : {total}")
                    print("-" * 40)
        else:
            print("Connection Failed!")
            print(f"Error: {data}")

    except Exception as e:
        print(f"Exception occurred: {e}")


# Run the test
if __name__ == "__main__":
    print("Testing Delta Exchange Testnet Connection...")
    print("=" * 40)
    get_wallet_balance()
