# =====================================================
# scanner.py - Multi-coin scanner loop
# =====================================================

from data_fetcher import fetch_candles_by_days
from indicators import add_all_indicators
from signal_engine import generate_signals
from config import SYMBOLS, BACKTEST_DAYS
import config


# Temporary stub until webhook_sender.py is built
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

        # Fetch all timeframes
        df_4h  = add_all_indicators(
            fetch_candles_by_days(symbol, "4h", days=BACKTEST_DAYS),
            params
        )

        df_1h = add_all_indicators(
            fetch_candles_by_days(symbol, "1h", days=BACKTEST_DAYS),
            params
        )

        df_15m = add_all_indicators(
            fetch_candles_by_days(symbol, "15m", days=BACKTEST_DAYS),
            params
        )

        # Align 4H trend to 1H candles

        trend_aligned = df_4h["trend"].reindex(
            df_1h.index,
            method="ffill"
        )

        # Generate signals
        signals_df = generate_signals(df_1h, trend_aligned)

        # Latest signal
        latest = signals_df.iloc[-1]

        signal = latest.get("signal")

        if signal:
            print(f"  SIGNAL : {symbol} -> {signal.upper()}")
        else:
            print(f"  SIGNAL : {symbol} -> NO SIGNAL")

    print("\n" + "=" * 55)
    print("  SCAN COMPLETE")
    print("=" * 55)