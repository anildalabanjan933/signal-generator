# =====================================================
# scanner.py - Multi-coin scanner loop
# =====================================================

from data_fetcher import fetch_candles_by_days          # FIX 1: use fetch_candles_by_days
from indicators import add_all_indicators               # FIX 2: correct function name
from signal_engine import scan_all_symbols              # FIX 3: use actual exported function
from config import SYMBOLS, BACKTEST_DAYS
import config


# FIX 4: Temporary stub until webhook_sender.py is built
def send_signal(symbol, signal_result):
    if signal_result.get("signal") in ("BUY", "SELL"):
        print(f"  [WEBHOOK] {symbol} -> {signal_result['signal']} (pending webhook_sender.py)")


def build_params():
    """Build indicator params dict from config defaults."""
    return {
        "ema_fast"              : config.EMA_FAST,
        "ema_slow"              : config.EMA_SLOW,
        "rsi_period"            : config.RSI_PERIOD,
        "rsi_oversold"          : config.RSI_OVERSOLD,
        "rsi_overbought"        : config.RSI_OVERBOUGHT,
        "adx_period"            : config.ADX_PERIOD,
        "adx_min_threshold"     : config.ADX_MIN_THRESHOLD,
        "atr_period"            : config.ATR_PERIOD,
        "atr_multiplier"        : config.ATR_MULTIPLIER,
        "supertrend_period"     : config.SUPERTREND_PERIOD,
        "supertrend_multiplier" : config.SUPERTREND_MULTIPLIER,
        "wt_channel_length"     : config.WT_CHANNEL_LENGTH,
        "wt_average_length"     : config.WT_AVERAGE_LENGTH,
        "wt_overbought"         : config.WT_OVERBOUGHT,
        "wt_oversold"           : config.WT_OVERSOLD,
        "chop_period"           : config.CHOP_PERIOD,
        "chop_threshold"        : config.CHOP_THRESHOLD,
    }


def run_scanner():
    print("\n" + "=" * 55)
    print("  SIGNAL SCANNER RUNNING")
    print("=" * 55)

    params = build_params()

    for symbol in SYMBOLS:
        print(f"\n  Scanning: {symbol}")
        print("  " + "-" * 40)

        # Fetch all timeframes with correct function and days from config
        df_4h  = add_all_indicators(fetch_candles_by_days(symbol, "4h",  days=BACKTEST_DAYS), params)
        df_1h  = add_all_indicators(fetch_candles_by_days(symbol, "1h",  days=BACKTEST_DAYS), params)
        df_15m = add_all_indicators(fetch_candles_by_days(symbol, "15m", days=BACKTEST_DAYS), params)

        # Run signal scan via signal_engine
        results = scan_all_symbols(
            symbols=[symbol],
            trend_tf="4h",
            trigger_tf="1h",
            params=params
        )

        for result in results:
            print(f"  Signal    : {result.get('signal', 'NONE')}")
            print(f"  Direction : {result.get('direction', '-')}")
            print(f"  Filters   : {result.get('filters_passed', '-')}")
            send_signal(symbol, result)

    print("\n" + "=" * 55)
    print("  SCAN COMPLETE")
    print("=" * 55)
