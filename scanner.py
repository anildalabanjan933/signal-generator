# =====================================================
# scanner.py - Multi-coin scanner loop
# =====================================================

from core.data_fetcher import fetch_candles_by_days
from core.indicators import add_all_indicators
from strategies.futures_4h_1h.strategy import generate_signals
from core.webhook_sender import *

from strategies.futures_4h_1h import config


def build_params():
    """Build indicator params dict from config defaults."""
    return {
        "ema_fast": config.EMA_FAST,
        "ema_slow": config.EMA_SLOW,
        "rsi_period": config.RSI_PERIOD,
        "rsi_oversold": config.RSI_OVERSOLD,
        "rsi_overbought": config.RSI_OVERBOUGHT,
        "adx_period": config.ADX_PERIOD,
        "adx_min_threshold": config.ADX_MIN_THRESHOLD,
        "atr_period": config.ATR_PERIOD,
        "atr_multiplier": config.ATR_MULTIPLIER,
        "supertrend_period": config.SUPERTREND_PERIOD,
        "supertrend_multiplier": config.SUPERTREND_MULTIPLIER,
        "wt_channel_length": config.WT_CHANNEL_LENGTH,
        "wt_average_length": config.WT_AVERAGE_LENGTH,
        "wt_overbought": config.WT_OVERBOUGHT,
        "wt_oversold": config.WT_OVERSOLD,
        "chop_period": config.CHOP_PERIOD,
        "chop_threshold": config.CHOP_THRESHOLD,
    }


def run_scanner():

    print("\n" + "=" * 55)
    print("  SIGNAL SCANNER RUNNING")
    print("=" * 55)

    params = build_params()

    for symbol in SYMBOLS:

        print(f"\n  Scanning: {symbol}")
        print("  " + "-" * 40)

        # =========================================
        # FETCH TIMEFRAMES
        # =========================================

        df_4h = add_all_indicators(
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

        print("  Scanner running...")
        print(f"  4H candles  : {len(df_4h)}")
        print(f"  1H candles  : {len(df_1h)}")
        print(f"  15M candles : {len(df_15m)}")

        # =========================================
        # GENERATE SIGNALS
        # =========================================

        signals_df = generate_signals(
            df_1h,
            trend_aligned=True,
        )

        # =========================================
        # LATEST SIGNAL
        # =========================================

        latest = signals_df.iloc[-1]

        signal = latest.get("signal")

        # =========================================
        # SIGNAL ROUTING
        # =========================================

        if signal:

            signal = signal.upper()

            print(f"  SIGNAL : {symbol} -> {signal}")

            # =====================================
            # BTC ROUTING
            # =====================================

            if symbol == "BTCUSD":

                if signal == "BUY":

                    print("  Sending BTC LONG ENTRY...")
                    send_btc_long_entry()

                elif signal == "SELL":

                    print("  Sending BTC SHORT ENTRY...")
                    send_btc_short_entry()

        else:

            print(f"  SIGNAL : {symbol} -> NO SIGNAL")

    print("\n" + "=" * 55)
    print("  SCAN COMPLETE")
    print("=" * 55)


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    run_scanner()