# ============================================================
# config.py - futures_2h_30m strategy settings
#
# FIXES APPLIED:
#   FIX1 - BACKTEST_DAYS raised from 90 to 730 (2 years)
#   FIX2 - Added EMA_WARMUP_BARS constant
#   FIX3 - Added ema200_proximity_atr_mult param
#   FIX4 - Added exit_mode, atr_sl_multiplier, atr_tp_multiplier,
#          trailing_atr_multiplier, taker_fee_pct, lot_size,
#          majority_vote_threshold to build_params()
#   FIX5 - Added build_params() helper function
#   FIX6 - LOT_SIZE replaced with per-symbol LOT_SIZES dict
#   FIX7 - TAKER_FEE_PCT corrected from 0.05 to 0.0005
#   FIX8 - USD_TO_INR conversion rate added
#   FIX9 - MAJORITY_VOTE_THRESHOLD added as explicit constant
#   FIX10 - build_params() updated with all missing keys
#   C1  - contract_value fallback changed to None
#   C2  - lot_size fallback changed to None
#   C3  - MIN_ATR_THRESHOLD added as named constant
#   C4  - use_trend_strength_filter added to build_params()
#   C5  - intraday_trend_tf and intraday_trigger_tf added
#   C6  - FIX4 comment corrected
#   C7  - USD_TO_INR updated to 85.0 (May 2026)
#   C8  - BNBUSD CONTRACT_VALUES corrected from 0.01 to 0.1
#          Verified from Delta Exchange API (May 2026).
#          Previous value was 10x understated.
#   C9  - Algotest section removed entirely.
#          Not used. Only Delta Exchange demo account
#          is used for forward testing.
# ============================================================

# --- Delta Exchange API ---
BASE_URL = "https://api.india.delta.exchange"

# --- Coins to scan ---
SYMBOLS = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "BNBUSD",
    "DOGEUSD",
]

# ============================================================
# TIMEFRAME SETTINGS
# trend  : 2h candles for trend direction
# trigger: 30m candles for entry signal
# ============================================================
TIMEFRAMES = {
    "trend"            : "2h",
    "trigger"          : "30m",
    "intraday_trend"   : "30m",
    "intraday_trigger" : "15m",
}

# Timeframe combinations to test during optimization
TIMEFRAME_COMBINATIONS = [
    ["2h", "30m"],
]

# ============================================================
# EMA SETTINGS
# ============================================================
EMA_FAST        = 50
EMA_SLOW        = 200

# Warmup guard: for EMA200 on 2H:
# 200 * 2 / 24 = 16.7 days minimum warmup.
# Recommend at least 3x = 50 days minimum.
EMA_WARMUP_BARS = EMA_SLOW

# Optimization ranges
EMA_FAST_RANGE  = {"min": 10,  "max": 100, "step": 10}
EMA_SLOW_RANGE  = {"min": 100, "max": 300, "step": 50}

# Fixed list overrides (leave empty [] to use range above)
EMA_FAST_LIST   = []
EMA_SLOW_LIST   = []

# ============================================================
# RSI SETTINGS
# ============================================================
RSI_PERIOD           = 14
RSI_OVERSOLD         = 30
RSI_OVERBOUGHT       = 70
TREND_RSI_MIN        = 60

# Optimization ranges
RSI_PERIOD_RANGE     = {"min": 7,  "max": 21, "step": 7}
RSI_OVERSOLD_RANGE   = {"min": 20, "max": 40, "step": 5}
RSI_OVERBOUGHT_RANGE = {"min": 60, "max": 80, "step": 5}
TREND_RSI_MIN_RANGE  = {"min": 50, "max": 65, "step": 5}

# Fixed list overrides
RSI_PERIOD_LIST      = []
RSI_OVERSOLD_LIST    = []
RSI_OVERBOUGHT_LIST  = []
TREND_RSI_MIN_LIST   = []

# ============================================================
# ADX SETTINGS
# ============================================================
ADX_PERIOD        = 14
ADX_MIN_THRESHOLD = 20

# Optimization ranges
ADX_PERIOD_RANGE  = {"min": 7,  "max": 21, "step": 7}
ADX_MIN_RANGE     = {"min": 15, "max": 30, "step": 5}

# Fixed list overrides
ADX_PERIOD_LIST   = []
ADX_MIN_LIST      = []

# ============================================================
# ATR SETTINGS
# ============================================================
ATR_PERIOD           = 14
ATR_MULTIPLIER       = 1.5

# Optimization ranges
ATR_PERIOD_RANGE     = {"min": 7,   "max": 21,  "step": 7}
ATR_MULTIPLIER_RANGE = {"min": 1.0, "max": 3.0, "step": 0.5}

# Fixed list overrides
ATR_PERIOD_LIST      = []
ATR_MULTIPLIER_LIST  = []

# ============================================================
# SUPERTREND SETTINGS
# ============================================================
SUPERTREND_PERIOD           = 10
SUPERTREND_MULTIPLIER       = 3.0

# Optimization ranges
SUPERTREND_PERIOD_RANGE     = {"min": 7,   "max": 20,  "step": 3}
SUPERTREND_MULTIPLIER_RANGE = {"min": 2.0, "max": 4.0, "step": 0.5}

# Fixed list overrides
SUPERTREND_PERIOD_LIST      = []
SUPERTREND_MULTIPLIER_LIST  = []

# ============================================================
# WAVETREND SETTINGS
# ============================================================
WT_CHANNEL_LENGTH = 9
WT_AVERAGE_LENGTH = 12
WT_OVERBOUGHT     = 60
WT_OVERSOLD       = -60

# Optimization ranges
WT_CHANNEL_RANGE  = {"min": 6,   "max": 14,  "step": 2}
WT_AVERAGE_RANGE  = {"min": 8,   "max": 20,  "step": 4}
WT_OB_RANGE       = {"min": 50,  "max": 70,  "step": 5}
WT_OS_RANGE       = {"min": -70, "max": -50, "step": 5}

# Fixed list overrides
WT_CHANNEL_LIST   = []
WT_AVERAGE_LIST   = []
WT_OB_LIST        = []
WT_OS_LIST        = []

# ============================================================
# CHOPPINESS INDEX SETTINGS
# ============================================================
CHOP_PERIOD          = 14
CHOP_THRESHOLD       = 61.8

# Optimization ranges
CHOP_PERIOD_RANGE    = {"min": 7,  "max": 21, "step": 7}
CHOP_THRESHOLD_RANGE = {"min": 50, "max": 70, "step": 5}

# Fixed list overrides
CHOP_PERIOD_LIST     = []
CHOP_THRESHOLD_LIST  = []

# ============================================================
# BACKTEST SETTINGS
# ============================================================
BACKTEST_DAYS   = 730
INITIAL_CAPITAL = 10000
RISK_PER_TRADE  = 0.01    # 1% risk per trade

# ============================================================
# SWING SYSTEM PARAMETERS
# ============================================================
EMA200_PROXIMITY_ATR_MULT = 1.0

# ============================================================
# EXIT MODE SETTINGS
#
# exit_mode options:
#   "opposite_signal" - exit when Supertrend flips
#   "atr_sl_tp"       - fixed ATR stoploss + take profit
#   "trailing_stop"   - ATR trailing stop, no fixed TP
# ============================================================
EXIT_MODE               = "opposite_signal"
ATR_SL_MULTIPLIER       = 1.5
ATR_TP_MULTIPLIER       = 3.0
TRAILING_ATR_MULTIPLIER = 4.0

# ============================================================
# TRADE EXECUTION SETTINGS
#
# Verified from Delta Exchange API (May 2026):
#   BTCUSD : 0.001 BTC/lot  → 100 lots = 0.1  BTC
#   ETHUSD : 0.01  ETH/lot  → 100 lots = 1.0  ETH
#   SOLUSD : 1     SOL/lot  →  10 lots = 10   SOL
#   BNBUSD : 0.1   BNB/lot  →   1 lot  = 0.1  BNB  (C8: was 0.01)
#   DOGEUSD: 100   DOGE/lot → 1000 lots = 100000 DOGE
#
# Delta Exchange does not support fractional lot sizes.
# Valid values: 1, 5, 10, 100, etc. (integers only)
# ============================================================
LOT_SIZES = {
    "BTCUSD" : 100,
    "ETHUSD" : 100,
    "SOLUSD" : 10,
    "BNBUSD" : 1,
    "AVAXUSD": 10,
    "DOGEUSD": 1000,
}

# Contract value per lot — used for USD PnL calculation
# C8: BNBUSD corrected from 0.01 to 0.1
CONTRACT_VALUES = {
    "BTCUSD" : 0.001,
    "ETHUSD" : 0.01,
    "SOLUSD" : 1,
    "BNBUSD" : 0.1,
    "AVAXUSD": 1,
    "DOGEUSD": 100,
}

# ============================================================
# FEE SETTINGS
# Taker: 0.05% = 0.0005 in decimal
# Maker: 0.02% = 0.0002 in decimal
# ============================================================
TAKER_FEE_PCT = 0.0005
MAKER_FEE_PCT = 0.0002

# ============================================================
# INR CONVERSION
# Used only in backtest report layer.
# Does not affect trade logic or signal generation.
# ============================================================
USD_TO_INR = 85.0

# ============================================================
# SIGNAL FILTER SETTINGS
# ============================================================
FILTER_CHOPPINESS     = True
FILTER_VOLATILITY     = True
FILTER_TREND_STRENGTH = True
FILTER_COIN_RANKING   = True
FILTER_CORRELATION    = True

MAJORITY_VOTE_THRESHOLD = 2

# ============================================================
# MIN ATR THRESHOLD
# Set > 0 to filter low-volatility bars from signal generation.
# ============================================================
MIN_ATR_THRESHOLD       = 0.0
MIN_ATR_THRESHOLD_RANGE = {"min": 0.0, "max": 0.005, "step": 0.001}

# ============================================================
# SCAN SETTINGS
# 1800 seconds = 30 min, aligned to 30m candle close
# ============================================================
SCAN_INTERVAL_SECONDS = 1800

# ============================================================
# OPTIMIZATION SETTINGS
# ============================================================
OPTIMIZATION_MODE = "both"
OPTIMIZE_FOR      = "profit_factor"
MAX_COMBINATIONS  = 500

# ============================================================
# OUTPUT SETTINGS
# ============================================================
SAVE_RESULTS_CSV = True
RESULTS_FOLDER   = "results"

# ============================================================
# build_params()
# ============================================================
def build_params(overrides: dict = None, symbol: str = None) -> dict:
    """
    Build the complete flat params dict for backtest_engine
    and indicators.add_all_indicators().

    Args:
        overrides : Optional dict of key/value pairs to override
                    any default. Used by optimizer.
        symbol    : Optional symbol string (e.g. "BTCUSD").
                    When provided, lot_size and contract_value
                    are resolved from LOT_SIZES and CONTRACT_VALUES.
                    When omitted, both default to None and
                    backtest_engine must raise ValueError.

    Returns:
        Flat dict with all required keys.
    """
    params = {
        # ── Timeframes ────────────────────────────────────────────
        "trend_tf"                  : TIMEFRAMES["trend"],
        "trigger_tf"                : TIMEFRAMES["trigger"],
        "intraday_trend_tf"         : TIMEFRAMES["intraday_trend"],
        "intraday_trigger_tf"       : TIMEFRAMES["intraday_trigger"],

        # ── EMA ───────────────────────────────────────────────────
        "ema_fast"                  : EMA_FAST,
        "ema_slow"                  : EMA_SLOW,

        # ── RSI ───────────────────────────────────────────────────
        "rsi_period"                : RSI_PERIOD,
        "rsi_oversold"              : RSI_OVERSOLD,
        "rsi_overbought"            : RSI_OVERBOUGHT,
        "trend_rsi_min"             : TREND_RSI_MIN,

        # ── ADX ───────────────────────────────────────────────────
        "adx_period"                : ADX_PERIOD,
        "adx_min_threshold"         : ADX_MIN_THRESHOLD,

        # ── ATR ───────────────────────────────────────────────────
        "atr_period"                : ATR_PERIOD,
        "atr_multiplier"            : ATR_MULTIPLIER,

        # ── Supertrend ────────────────────────────────────────────
        "supertrend_period"         : SUPERTREND_PERIOD,
        "supertrend_multiplier"     : SUPERTREND_MULTIPLIER,

        # ── WaveTrend ─────────────────────────────────────────────
        "wt_channel_length"         : WT_CHANNEL_LENGTH,
        "wt_average_length"         : WT_AVERAGE_LENGTH,
        "wt_overbought"             : WT_OVERBOUGHT,
        "wt_oversold"               : WT_OVERSOLD,

        # ── Choppiness ────────────────────────────────────────────
        "chop_period"               : CHOP_PERIOD,
        "chop_threshold"            : CHOP_THRESHOLD,

        # ── Swing system ──────────────────────────────────────────
        "ema200_proximity_atr_mult" : EMA200_PROXIMITY_ATR_MULT,

        # ── Exit mode ─────────────────────────────────────────────
        "exit_mode"                 : EXIT_MODE,
        "atr_sl_multiplier"         : ATR_SL_MULTIPLIER,
        "atr_tp_multiplier"         : ATR_TP_MULTIPLIER,
        "trailing_atr_multiplier"   : TRAILING_ATR_MULTIPLIER,

        # ── Filters ───────────────────────────────────────────────
        "use_choppiness_filter"     : FILTER_CHOPPINESS,
        "use_volatility_filter"     : FILTER_VOLATILITY,
        "use_trend_strength_filter" : FILTER_TREND_STRENGTH,
        "choppiness_threshold"      : CHOP_THRESHOLD,
        "min_atr_threshold"         : MIN_ATR_THRESHOLD,
        "use_coin_ranking_filter"   : FILTER_COIN_RANKING,
        "use_correlation_filter"    : FILTER_CORRELATION,

        # ── Signal voting ─────────────────────────────────────────
        "majority_vote_threshold"   : MAJORITY_VOTE_THRESHOLD,

        # ── Trade execution ───────────────────────────────────────
        "lot_size"                  : LOT_SIZES.get(symbol) if symbol else None,
        "contract_value"            : CONTRACT_VALUES.get(symbol) if symbol else None,
        "taker_fee_pct"             : TAKER_FEE_PCT,
        "maker_fee_pct"             : MAKER_FEE_PCT,

        # ── Reporting ─────────────────────────────────────────────
        "usd_to_inr"                : USD_TO_INR,

        # ── Backtest ──────────────────────────────────────────────
        "backtest_days"             : BACKTEST_DAYS,
        "initial_capital"           : INITIAL_CAPITAL,
        "risk_per_trade"            : RISK_PER_TRADE,
    }

    if overrides:
        params.update(overrides)

    return params
