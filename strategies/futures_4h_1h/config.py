# ============================================================
# config.py - All settings in one place (Fully Optimizable)
#
# FIXES APPLIED:
#   FIX1 - BACKTEST_DAYS raised from 90 to 730 (2 years)
#          EMA200 on 4H needs 33 days warmup alone.
#          90 days produces statistically meaningless results.
#          730 days gives ~697 usable days after warmup.
#
#   FIX2 - Added EMA_WARMUP_BARS constant so backtest_engine
#          can warn when days is insufficient for the slow EMA.
#
#   FIX3 - Added ema200_proximity_atr_mult param (was missing).
#          backtest_engine._near_ema200() reads this value.
#          Without it, DEFAULT_EMA200_PROXIMITY_MULT=1.0 is used
#          silently — now it is explicit and tunable.
#
#   FIX4 - Added exit_mode, atr_sl_multiplier, atr_tp_multiplier,
#          trailing_atr_multiplier, taker_fee_pct, lot_size,
#          majority_vote_threshold to build_params().
#          These were read by backtest_engine but never defined
#          in config, causing params.get() to silently fall back
#          to hardcoded defaults with no visibility.
#
#   FIX5 - Added build_params() helper function.
#          Assembles the flat params dict that backtest_engine
#          and indicators.add_all_indicators() both expect.
#          Eliminates repeated dict construction across files.
#
#   FIX6 - LOT_SIZE replaced with per-symbol LOT_SIZES dict.
#          Single global LOT_SIZE=1 was wrong for both symbols.
#          BTCUSD: 100 lots = 0.1 BTC (0.001 BTC/lot)
#          ETHUSD: 100 lots = 1.0 ETH (0.01  ETH/lot)
#          CONTRACT_VALUES dict added for PnL calculation.
#          Both verified from Delta Exchange API.
#
#   FIX7 - TAKER_FEE_PCT corrected from 0.05 to 0.0005.
#          0.05 was being interpreted as 5% per trade (100x too high).
#          Delta Exchange taker fee is 0.05% = 0.0005 in decimal.
#          MAKER_FEE_PCT = 0.0002 (0.02%) also added explicitly.
#
#   FIX8 - USD_TO_INR conversion rate added for INR reporting.
#          Used only in backtest report layer.
#          Does not affect any trade logic or signal generation.
#
#   FIX9 - MAJORITY_VOTE_THRESHOLD added as explicit constant.
#          Was referenced in FIX4 comment but never defined.
#          build_params() was returning None for this key silently.
#
#   FIX10 - build_params() updated:
#            - Added symbol argument for per-symbol lot_size
#              and contract_value lookup.
#            - Added missing keys: majority_vote_threshold,
#              use_coin_ranking_filter, use_correlation_filter,
#              contract_value, maker_fee_pct, usd_to_inr.
#            - FILTER_COIN_RANKING and FILTER_CORRELATION were
#              defined at top level but never passed into params.
#
#   C1  - contract_value fallback changed from 0.001 to None.
#          Fallback of 0.001 (BTCUSD value) was silently wrong
#          for any unknown symbol. None forces an explicit error
#          in backtest_engine instead of a silent wrong PnL.
#
#   C2  - lot_size fallback changed from 1 to None.
#          Fallback of 1 lot was silently wrong for any symbol
#          not in LOT_SIZES. None forces an explicit error
#          in backtest_engine instead of silent undersizing.
#
#   C3  - MIN_ATR_THRESHOLD added as a named top-level constant.
#          Was previously hardcoded as 0.0 inside build_params()
#          with no visibility, no optimization range, no comment.
#
#   C4  - use_trend_strength_filter added to build_params().
#          FILTER_TREND_STRENGTH was defined at top level but
#          never passed into the params dict. Any engine or
#          signal code reading this key was getting None silently.
#
#   C5  - intraday_trend_tf and intraday_trigger_tf added to
#          build_params(). Both timeframes were defined in
#          TIMEFRAMES dict but never forwarded into params.
#
#   C6  - FIX4 comment corrected: "BACKTEST_PARAMS" replaced
#          with "build_params()". BACKTEST_PARAMS dict never
#          existed; the comment was misleading.
#
#   C7  - USD_TO_INR updated to 85.0 (May 2026 approximate).
#          Previous value of 84.0 was stale.
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
# Both trend and trigger are fully customizable
# Valid values: "1m","3m","5m","15m","30m","1h","2h","4h","6h","1d","1w"
# ============================================================
TIMEFRAMES = {
    "trend"            : "4h",
    "trigger"          : "1h",
    "intraday_trend"   : "1h",
    "intraday_trigger" : "15m"
}

# Timeframe combinations to test during optimization
# Each pair = [trend_tf, trigger_tf]
TIMEFRAME_COMBINATIONS = [
    ["4h", "1h"],    # Swing default
    ["1d", "4h"],    # Longer swing
    ["1h", "15m"],   # Intraday default
    ["15m", "5m"],   # Scalping
]

# ============================================================
# EMA SETTINGS
# ============================================================
EMA_FAST        = 50       # Fast EMA period  → produces column "ema50"
EMA_SLOW        = 200      # Slow EMA period  → produces column "ema200"

# FIX2: Warmup guard constant.
# backtest_engine warns if BACKTEST_DAYS < EMA_WARMUP_BARS * trend_tf_hours / 24
# For EMA200 on 4H: 200 * 4 / 24 = 33.3 days minimum warmup.
# Recommend at least 3x warmup = 100 days minimum, 730 days for reliable stats.
EMA_WARMUP_BARS = EMA_SLOW   # = 200 bars on the trend TF

# Optimization ranges (min, max, step)
EMA_FAST_RANGE  = {"min": 10,  "max": 100, "step": 10}
EMA_SLOW_RANGE  = {"min": 100, "max": 300, "step": 50}

# Fixed list override (optional - leave empty [] to use range above)
EMA_FAST_LIST   = []
EMA_SLOW_LIST   = []

# ============================================================
# RSI SETTINGS
# ============================================================
RSI_PERIOD           = 14
RSI_OVERSOLD         = 30
RSI_OVERBOUGHT       = 70

# 4H trend momentum filter
# Trade only when higher timeframe momentum is strong
TREND_RSI_MIN        = 60

# Optimization ranges
RSI_PERIOD_RANGE     = {"min": 7,  "max": 21, "step": 7}
RSI_OVERSOLD_RANGE   = {"min": 20, "max": 40, "step": 5}
RSI_OVERBOUGHT_RANGE = {"min": 60, "max": 80, "step": 5}

# Trend RSI optimization range
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
# FIX1: BACKTEST_DAYS raised from 90 to 730.
#
# Minimum days required for EMA200 on 4H to be meaningful:
#   Warmup only  : EMA_SLOW * trend_tf_hours / 24 = 200*4/24 = 33 days
#   Recommended  : 3x warmup = ~100 days minimum
#   For stats    : 730 days (2 years) gives ~50-150 swing trades
#                  which is the minimum for statistically valid PF/WR
#
# If you must use fewer days (e.g. for a new coin), set
# BACKTEST_DAYS >= 180 and accept that early EMA200 values
# are less reliable.
# ============================================================
BACKTEST_DAYS    = 730     # FIX1: was 90, now 730 (2 years)
INITIAL_CAPITAL  = 10000
RISK_PER_TRADE   = 0.01    # 1% risk per trade

# ============================================================
# SWING SYSTEM PARAMETERS
# FIX3: ema200_proximity_atr_mult was missing entirely.
#       backtest_engine._near_ema200() uses this to define
#       "price near EMA200" as: abs(close - ema200) <= atr * mult
#
# Tuning guide:
#   0.5 = very tight (price must be almost touching EMA200)
#   1.0 = standard  (within 1 ATR of EMA200)
#   1.5 = loose     (wider pullback zone, more trades, more noise)
#   2.0 = very loose (catches extended pullbacks)
#
# Start with 1.0. If 0 trades, loosen to 1.5 or 2.0.
# If too many low-quality trades, tighten to 0.5.
# ============================================================
EMA200_PROXIMITY_ATR_MULT = 1.0   # FIX3: was missing

# ============================================================
# ============================================================
# EXIT MODE SETTINGS
# ============================================================
#
# exit_mode options:
#   "opposite_signal" - exit when Supertrend flips
#   "atr_sl_tp"       - fixed ATR stoploss + take profit
#   "trailing_stop"   - ATR trailing stop, no fixed TP
#
# Current test:
#   wider ATR trailing stop for crypto trend capture
# ============================================================

EXIT_MODE = "opposite_signal"
ATR_SL_MULTIPLIER       = 1.5
ATR_TP_MULTIPLIER       = 3.0
TRAILING_ATR_MULTIPLIER = 4.0
# ============================================================

# TRADE EXECUTION SETTINGS
# FIX6: LOT_SIZE replaced with per-symbol LOT_SIZES dict.
#       Single global LOT_SIZE=1 was wrong for both symbols.
#
# Verified from Delta Exchange API (May 2026):
#   BTCUSD contract_value = 0.001 BTC/lot
#     → 100 lots = 0.1 BTC per trade
#   ETHUSD contract_value = 0.01 ETH/lot
#     → 100 lots = 1.0 ETH per trade
#
# Delta Exchange does not support fractional lot sizes.
# Valid values: 1, 5, 10, 100, etc. (integers only)
#
# C1: contract_value fallback is None (not 0.001).
#     backtest_engine must raise ValueError if None is received.
#
# C2: lot_size fallback is None (not 1).
#     backtest_engine must raise ValueError if None is received.
# ============================================================
LOT_SIZES = {
    "BTCUSD": 100,
    "ETHUSD": 100,
    "SOLUSD": 10,
    "BNBUSD": 1,
    "AVAXUSD": 10,
    "DOGEUSD": 1000,
}

# Contract value per lot — used for USD PnL calculation
# Verified from Delta Exchange API (May 2026)
CONTRACT_VALUES = {
    "BTCUSD": 0.001,
    "ETHUSD": 0.01,
    "SOLUSD": 1,
    "BNBUSD": 0.01,
    "AVAXUSD": 1,
    "DOGEUSD": 100,
}
# ============================================================
# FEE SETTINGS
# FIX7: TAKER_FEE_PCT corrected from 0.05 to 0.0005.
#       Previous value of 0.05 = 5% per trade (100x too high).
#       Delta Exchange verified fees (May 2026):
#         Taker: 0.05% = 0.0005 in decimal
#         Maker: 0.02% = 0.0002 in decimal
#       Backtest engine must multiply fee * notional_value
#       using these decimal forms directly.
# ============================================================
TAKER_FEE_PCT = 0.0005   # FIX7: was 0.05 (5%), corrected to 0.0005 (0.05%)
MAKER_FEE_PCT = 0.0002   # FIX7: added explicitly (0.02%)

# ============================================================
# INR CONVERSION
# FIX8: Added for backtest PnL reporting in INR.
#       Used only in the report layer — does not affect
#       any trade logic, signal generation, or sizing.
# C7:   Updated from 84.0 to 85.0 (May 2026 approximate).
#       Update this value periodically to reflect current rate.
# ============================================================
USD_TO_INR = 85.0   # C7: updated from 84.0; update as needed

# ============================================================
# SIGNAL FILTER SETTINGS
# ============================================================
FILTER_CHOPPINESS     = True
FILTER_VOLATILITY     = True
FILTER_TREND_STRENGTH = True
FILTER_COIN_RANKING   = True
FILTER_CORRELATION    = True

# FIX9: MAJORITY_VOTE_THRESHOLD was referenced in FIX4 comment
#       but never defined as a constant. build_params() was
#       returning None for this key silently.
#
# Meaning: minimum number of confirming signals required
# before a trade is taken. Increase to reduce noise.
#   1 = any single signal fires a trade (too loose)
#   2 = at least 2 signals must agree (recommended)
#   3 = all 3 signals must agree (very selective)
MAJORITY_VOTE_THRESHOLD = 2   # FIX9: was missing

# ============================================================
# C3: MIN_ATR_THRESHOLD added as a named top-level constant.
#     Was previously hardcoded as 0.0 inside build_params()
#     with no visibility, no optimization range, no comment.
#     Set > 0 to filter low-volatility bars from signal generation.
# ============================================================
MIN_ATR_THRESHOLD = 0.0

# Optimization range for MIN_ATR_THRESHOLD (optional)
MIN_ATR_THRESHOLD_RANGE = {"min": 0.0, "max": 0.005, "step": 0.001}

# ============================================================
# SCAN SETTINGS
# ============================================================
SCAN_INTERVAL_SECONDS = 900    # Scan every 15 minutes

# ============================================================
# OPTIMIZATION SETTINGS
# ============================================================
OPTIMIZATION_MODE = "both"     # "grid" | "range" | "both"
OPTIMIZE_FOR      = "profit_factor"
MAX_COMBINATIONS  = 500

# ============================================================
# OUTPUT SETTINGS
# ============================================================
SAVE_RESULTS_CSV = True
RESULTS_FOLDER   = "results"

# ============================================================
# ALGOTEST WEBHOOKS
# ============================================================

BTC_LONG_ENTRY_WEBHOOK = "https://api.algotest.in/webhook/custom/execution/start/6a009c61f85d2617ff7e2126"
BTC_LONG_EXIT_WEBHOOK  = "https://api.algotest.in/webhook/custom/execution/square_off/6a009c61f85d2617ff7e2126"

BTC_SHORT_ENTRY_WEBHOOK = "https://api.algotest.in/webhook/custom/execution/start/6a009ec8053920297050fcc6"
BTC_SHORT_EXIT_WEBHOOK  = "https://api.algotest.in/webhook/custom/execution/square_off/6a009ec8053920297050fcc6"


# ============================================================
# ALGOTEST JSON PAYLOADS
# ============================================================

BTC_LONG_ENTRY_PAYLOAD = {"access_token":"n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9","alert_name":"Future buy python signal_Custom"}



BTC_LONG_EXIT_PAYLOAD = {"access_token":"n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9","alert_name":"Future buy python signal_Custom"}



BTC_SHORT_ENTRY_PAYLOAD = {"access_token":"n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9","alert_name":"BTC-FUT -PYTN-SELL 4H 1H_Custom"}

BTC_SHORT_EXIT_PAYLOAD = {"access_token":"n7FJcMHANHN4F8HdqbU5QMDJn5JO79K9","alert_name":"BTC-FUT -PYTN-SELL 4H 1H_Custom"}

# ============================================================
# FIX5 + FIX10 + C1-C7: build_params()
#
#   FIX10 changes vs original:
#     - Added symbol argument → per-symbol lot_size
#       and contract_value resolved here, not in engine.
#     - Added majority_vote_threshold (was missing → None).
#     - Added use_coin_ranking_filter (was defined but
#       never passed into params dict).
#     - Added use_correlation_filter (same issue).
#     - Added contract_value key for PnL calculation.
#     - Added maker_fee_pct (only taker was present before).
#     - Added usd_to_inr for report layer conversion.
#
#   C1: contract_value fallback is now None — not 0.001.
#       backtest_engine must raise ValueError on None.
#   C2: lot_size fallback is now None — not 1.
#       backtest_engine must raise ValueError on None.
#   C3: min_atr_threshold now reads MIN_ATR_THRESHOLD constant.
#   C4: use_trend_strength_filter added (was missing entirely).
#   C5: intraday_trend_tf + intraday_trigger_tf added.
#   C6: FIX4 comment corrected to reference build_params().
# ============================================================
def build_params(overrides: dict = None, symbol: str = None) -> dict:
    """
    Build the complete flat params dict for backtest_engine
    and indicators.add_all_indicators().

    Args:
        overrides : Optional dict of key/value pairs to override
                    any default value. Used by the optimizer to
                    test different parameter combinations without
                    modifying config constants.
        symbol    : Optional symbol string (e.g. "BTCUSD").
                    When provided, lot_size and contract_value
                    are resolved from LOT_SIZES and CONTRACT_VALUES.
                    When omitted, both default to None and
                    backtest_engine must raise ValueError.

    Returns:
        Flat dict with all required keys.

    Raises (via backtest_engine):
        ValueError if lot_size or contract_value is None,
        meaning the symbol was not found in LOT_SIZES or
        CONTRACT_VALUES. Add the symbol to config.py to fix.

    Example:
        # Symbol-aware (recommended for backtesting)
        params = config.build_params(symbol="BTCUSD")

        # Override for optimization run
        params = config.build_params(
            symbol="ETHUSD",
            overrides={"ema_fast": 20, "ema_slow": 100, "exit_mode": "atr_sl_tp"}
        )
    """
    params = {
        # ── Timeframes ────────────────────────────────────────────
        "trend_tf"                   : TIMEFRAMES["trend"],
        "trigger_tf"                 : TIMEFRAMES["trigger"],
        "intraday_trend_tf"          : TIMEFRAMES["intraday_trend"],    # C5: was missing
        "intraday_trigger_tf"        : TIMEFRAMES["intraday_trigger"],  # C5: was missing

        # ── EMA ───────────────────────────────────────────────────
        "ema_fast"                   : EMA_FAST,
        "ema_slow"                   : EMA_SLOW,

        # ── RSI ───────────────────────────────────────────────────
        "rsi_period"                 : RSI_PERIOD,
        "rsi_oversold"               : RSI_OVERSOLD,
        "rsi_overbought"             : RSI_OVERBOUGHT,
        "trend_rsi_min"              : TREND_RSI_MIN,

        # ── ADX ───────────────────────────────────────────────────
        "adx_period"                 : ADX_PERIOD,
        "adx_min_threshold"          : ADX_MIN_THRESHOLD,

        # ── ATR ───────────────────────────────────────────────────
        "atr_period"                 : ATR_PERIOD,
        "atr_multiplier"             : ATR_MULTIPLIER,

        # ── Supertrend ────────────────────────────────────────────
        "supertrend_period"          : SUPERTREND_PERIOD,
        "supertrend_multiplier"      : SUPERTREND_MULTIPLIER,

        # ── WaveTrend ─────────────────────────────────────────────
        "wt_channel_length"          : WT_CHANNEL_LENGTH,
        "wt_average_length"          : WT_AVERAGE_LENGTH,
        "wt_overbought"              : WT_OVERBOUGHT,
        "wt_oversold"                : WT_OVERSOLD,

        # ── Choppiness ────────────────────────────────────────────
        "chop_period"                : CHOP_PERIOD,
        "chop_threshold"             : CHOP_THRESHOLD,

        # ── Swing system ──────────────────────────────────────────
        "ema200_proximity_atr_mult"  : EMA200_PROXIMITY_ATR_MULT,

        # ── Exit mode ─────────────────────────────────────────────
        "exit_mode"                  : EXIT_MODE,
        "atr_sl_multiplier"          : ATR_SL_MULTIPLIER,
        "atr_tp_multiplier"          : ATR_TP_MULTIPLIER,
        "trailing_atr_multiplier"    : TRAILING_ATR_MULTIPLIER,

        # ── Filters ───────────────────────────────────────────────
        "use_choppiness_filter"      : FILTER_CHOPPINESS,
        "use_volatility_filter"      : FILTER_VOLATILITY,
        "use_trend_strength_filter"  : FILTER_TREND_STRENGTH,          # C4: was missing
        "choppiness_threshold"       : CHOP_THRESHOLD,
        "min_atr_threshold"          : MIN_ATR_THRESHOLD,              # C3: now a named constant
        "use_coin_ranking_filter"    : FILTER_COIN_RANKING,            # FIX10: was missing
        "use_correlation_filter"     : FILTER_CORRELATION,             # FIX10: was missing

        # ── Signal voting ─────────────────────────────────────────
        "majority_vote_threshold"    : MAJORITY_VOTE_THRESHOLD,        # FIX9+FIX10: was missing

        # ── Trade execution ───────────────────────────────────────
        # C1: fallback is None — backtest_engine must raise ValueError on None
        # C2: fallback is None — backtest_engine must raise ValueError on None
        "lot_size"                   : LOT_SIZES.get(symbol) if symbol else None,
        "contract_value"             : CONTRACT_VALUES.get(symbol) if symbol else None,
        "taker_fee_pct"              : TAKER_FEE_PCT,                  # FIX7: 0.0005
        "maker_fee_pct"              : MAKER_FEE_PCT,                  # FIX10: was missing

        # ── Reporting ─────────────────────────────────────────────
        "usd_to_inr"                 : USD_TO_INR,                     # FIX8+FIX10: was missing

        # ── Backtest ──────────────────────────────────────────────
        "backtest_days"              : BACKTEST_DAYS,
        "initial_capital"            : INITIAL_CAPITAL,
        "risk_per_trade"             : RISK_PER_TRADE,
    }

    # Apply any overrides (used by optimizer)
    if overrides:
        params.update(overrides)

    return params
