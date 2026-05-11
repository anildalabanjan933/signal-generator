# =====================================================
# optimizer.py
# Delta Exchange - Swing Strategy Parameter Optimizer
#
# WHAT IT DOES:
#   Grid search over parameter ranges defined in config.
#   Runs backtest for each parameter combination.
#   Ranks results by profit factor (primary) and
#   net PnL % (secondary).
#   Saves all results to CSV + best params to JSON.
#
# USAGE:
#   python optimizer.py
#   or imported and called via run_optimization()
#
# OUTPUT FILES (in ./results/):
#   optimizer_results_<label>_<timestamp>.csv
#   best_params_<symbol>_<label>_<timestamp>.json
# =====================================================

import os
import json
import itertools
import traceback
import pandas as pd
from datetime import datetime
from copy import deepcopy

from core.data_fetcher import fetch_mtf_candles
from backtest import (
    run_backtest,
    calculate_metrics,
    calculate_periodic_pnl,
    print_periodic_pnl,
)
import config


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
RESULTS_DIR = "../../results"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _make_filename(prefix: str, symbol: str, label: str, ext: str) -> str:
    """Build clean filename with no double underscore."""
    label_part = f"_{label}" if label else ""
    ts = _timestamp_str()
    return f"{RESULTS_DIR}/{prefix}_{symbol}{label_part}_{ts}.{ext}"


def _format_duration(seconds: float) -> str:
    """Format elapsed seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


# ─────────────────────────────────────────────
# PARAMETER GRID BUILDER
# ─────────────────────────────────────────────
def build_param_grid(optimization_ranges: dict) -> list:
    """
    Build all parameter combinations from optimization ranges.

    optimization_ranges format (from config):
    {
        "atr_sl_multiplier"        : [1.0, 1.5, 2.0],
        "atr_tp_multiplier"        : [2.0, 3.0, 4.0],
        "adx_min_threshold"        : [20, 25],
        "ema200_proximity_atr_mult": [0.5, 1.0, 1.5],
    }

    Returns list of dicts, each a full parameter combination.
    Example:
    [
        {"atr_sl_multiplier": 1.0, "atr_tp_multiplier": 2.0, ...},
        {"atr_sl_multiplier": 1.0, "atr_tp_multiplier": 3.0, ...},
        ...
    ]
    """
    if not optimization_ranges:
        return []

    keys   = list(optimization_ranges.keys())
    values = list(optimization_ranges.values())

    # Ensure all values are lists
    for i, v in enumerate(values):
        if not isinstance(v, list):
            values[i] = [v]

    combinations = list(itertools.product(*values))

    grid = []
    for combo in combinations:
        param_set = dict(zip(keys, combo))
        grid.append(param_set)

    return grid


# ─────────────────────────────────────────────
# SINGLE COMBINATION RUNNER
# ─────────────────────────────────────────────
def _run_single_combination(
    symbol: str,
    df_trend: pd.DataFrame,
    df_trigger: pd.DataFrame,
    base_params: dict,
    override_params: dict,
    combo_index: int,
    total_combos: int,
) -> dict | None:
    """
    Run backtest for one parameter combination.
    Merges override_params into a copy of base_params.
    Returns metrics dict with override params embedded,
    or None if backtest fails.

    Args:
        symbol          : e.g. 'BTCUSD'
        df_trend        : Pre-fetched 4H DataFrame
        df_trigger      : Pre-fetched 1H DataFrame
        base_params     : Full base config dict
        override_params : Parameter overrides for this combination
        combo_index     : 1-based index for progress logging
        total_combos    : Total number of combinations

    Returns:
        dict with metrics + override params, or None on error
    """
    # Deep copy to avoid mutation across combinations
    params = deepcopy(base_params)
    params.update(override_params)

    try:
        trades  = run_backtest(symbol, df_trend.copy(), df_trigger.copy(), params)
        metrics = calculate_metrics(trades, symbol)

        # Embed override params into result row for CSV output
        result = {**metrics, **override_params}
        result["combo_index"] = combo_index

        pct_done = (combo_index / total_combos) * 100
        print(
            f"    [{combo_index:>4}/{total_combos}  {pct_done:>5.1f}%]  "
            f"trades={metrics['total_trades']:>4}  "
            f"PF={metrics['profit_factor']:>6.3f}  "
            f"net={metrics['total_pnl_pct_net']:>8.2f}%  "
            f"win={metrics['win_rate_pct']:>5.1f}%  "
            f"dd={metrics['max_drawdown_pct']:>6.2f}%  "
            f"| {override_params}"
        )

        return result

    except Exception as e:
        print(
            f"    [{combo_index:>4}/{total_combos}]  "
            f"ERROR: {e}  | {override_params}"
        )
        return None


# ─────────────────────────────────────────────
# RESULTS RANKER
# ─────────────────────────────────────────────
def _rank_results(results: list, min_trades: int = 10) -> pd.DataFrame:
    """
    Rank optimization results.

    Ranking criteria (in order):
      1. Must have >= min_trades (filter out under-traded combos)
      2. Sort by profit_factor DESC
      3. Then by total_pnl_pct_net DESC
      4. Then by win_rate_pct DESC

    Args:
        results    : List of result dicts from _run_single_combination
        min_trades : Minimum trades required to be included in ranking

    Returns:
        Ranked DataFrame, best combination first
    """
    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # Filter out failed runs (None was excluded before this call)
    # and combos with too few trades
    df = df[df["total_trades"] >= min_trades].copy()

    if df.empty:
        return df

    df = df.sort_values(
        by        = ["profit_factor", "total_pnl_pct_net", "win_rate_pct"],
        ascending = [False, False, False]
    ).reset_index(drop=True)

    df.insert(0, "rank", df.index + 1)

    return df


# ─────────────────────────────────────────────
# BEST PARAMS SAVER
# ─────────────────────────────────────────────
def _save_best_params(
    best_row: pd.Series,
    override_keys: list,
    base_params: dict,
    symbol: str,
    label: str
) -> str:
    """
    Save the best parameter combination to a JSON file.
    Merges best override params into base_params for a
    complete, ready-to-use config.

    Args:
        best_row      : Top-ranked row from results DataFrame
        override_keys : List of param keys that were optimized
        base_params   : Original base config dict
        symbol        : Trading symbol
        label         : Optional label for filename

    Returns:
        Path to saved JSON file
    """
    _ensure_results_dir()

    best_overrides = {
        k: best_row[k]
        for k in override_keys
        if k in best_row.index
    }

    # Build complete params: base + best overrides
    full_params = deepcopy(base_params)
    full_params.update(best_overrides)

    # Add metadata
    output = {
        "symbol"         : symbol,
        "optimized_at"   : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rank_1_metrics" : {
            "total_trades"      : int(best_row.get("total_trades",      0)),
            "profit_factor"     : float(best_row.get("profit_factor",   0)),
            "win_rate_pct"      : float(best_row.get("win_rate_pct",    0)),
            "total_pnl_pct_net" : float(best_row.get("total_pnl_pct_net", 0)),
            "total_pnl_usd_net" : float(best_row.get("total_pnl_usd_net", 0)),
            "total_pnl_inr_net" : float(best_row.get("total_pnl_inr_net", 0)),
            "max_drawdown_pct"  : float(best_row.get("max_drawdown_pct", 0)),
        },
        "best_params"    : full_params,
        "optimized_keys" : override_keys,
    }

    filename = _make_filename("best_params", symbol, label, "json")

    with open(filename, "w") as f:
        json.dump(output, f, indent=4, default=str)

    return filename


# ─────────────────────────────────────────────
# PER-SYMBOL OPTIMIZER
# ─────────────────────────────────────────────
def optimize_symbol(
    symbol: str,
    base_params: dict,
    optimization_ranges: dict,
    label: str          = "",
    min_trades: int     = 10,
    top_n: int          = 10,
) -> pd.DataFrame:
    """
    Run full grid optimization for a single symbol.

    Steps:
      1. Fetch MTF data once (reused across all combinations)
      2. Build parameter grid from optimization_ranges
      3. Run backtest for each combination
      4. Rank results
      5. Save ranked CSV + best params JSON
      6. Print top N results to terminal

    Args:
        symbol              : e.g. 'BTCUSD'
        base_params         : Full base config dict
        optimization_ranges : Dict of param -> list of values to test
        label               : Optional label for file naming
        min_trades          : Minimum trades to include in ranking
        top_n               : How many top results to print

    Returns:
        Ranked DataFrame of all results (empty if failed)
    """
    import time
    start_time = time.time()

    trend_tf   = base_params.get("trend_tf",   "4h")
    trigger_tf = base_params.get("trigger_tf", "1h")
    days       = base_params.get(
        "backtest_days",
        getattr(config, "BACKTEST_DAYS", 365)
    )

    print(f"\n{'='*70}")
    print(f"  OPTIMIZER  |  {symbol}  |  {trend_tf}/{trigger_tf}  |  {days} days")
    print(f"{'='*70}")

    # ── Build grid ────────────────────────────────────────────────
    grid = build_param_grid(optimization_ranges)

    if not grid:
        print(f"  [ERROR] optimization_ranges is empty. Nothing to optimize.")
        return pd.DataFrame()

    total_combos = len(grid)
    print(
        f"  Parameters : {list(optimization_ranges.keys())}\n"
        f"  Grid size  : {total_combos} combinations\n"
        f"  Min trades : {min_trades}"
    )

    # ── Fetch data once ───────────────────────────────────────────
    print(f"\n  Fetching MTF data for {symbol} ...")
    mtf_data   = fetch_mtf_candles(
        symbol,
        days             = days,
        trend_resolution = trend_tf,
        entry_resolution = trigger_tf
    )
    df_trend   = mtf_data["trend"]
    df_trigger = mtf_data["entry"]

    if df_trend.empty or df_trigger.empty:
        print(f"  [ERROR] Failed to fetch data for {symbol}. Skipping.")
        return pd.DataFrame()

    print(
        f"  Data ready : "
        f"trend={len(df_trend)} candles  "
        f"entry={len(df_trigger)} candles\n"
    )

    # ── Run grid ──────────────────────────────────────────────────
    print(f"  Running {total_combos} combinations ...\n")
    results = []

    for i, override_params in enumerate(grid, start=1):
        result = _run_single_combination(
            symbol          = symbol,
            df_trend        = df_trend,
            df_trigger      = df_trigger,
            base_params     = base_params,
            override_params = override_params,
            combo_index     = i,
            total_combos    = total_combos,
        )
        if result is not None:
            results.append(result)

    # ── Rank ──────────────────────────────────────────────────────
    ranked_df = _rank_results(results, min_trades=min_trades)

    elapsed = time.time() - start_time
    print(
        f"\n  Completed  : {total_combos} combinations in "
        f"{_format_duration(elapsed)}"
    )

    if ranked_df.empty:
        print(
            f"  [WARNING] No combinations met the min_trades={min_trades} "
            f"threshold. Try lowering min_trades or increasing backtest_days."
        )
        return pd.DataFrame()

    # ── Save CSV ──────────────────────────────────────────────────
    _ensure_results_dir()
    csv_path = _make_filename("optimizer_results", symbol, label, "csv")
    ranked_df.to_csv(csv_path, index=False)
    print(f"  Results CSV: {csv_path}")

    # ── Save best params JSON ─────────────────────────────────────
    best_row    = ranked_df.iloc[0]
    override_keys = list(optimization_ranges.keys())
    json_path   = _save_best_params(
        best_row      = best_row,
        override_keys = override_keys,
        base_params   = base_params,
        symbol        = symbol,
        label         = label
    )
    print(f"  Best params: {json_path}")

    # ── Print top N ───────────────────────────────────────────────
    _print_top_results(ranked_df, symbol, top_n, override_keys)

    # ── Print periodic PnL for best combo ─────────────────────────
    _print_best_combo_periodic(
        symbol          = symbol,
        df_trend        = df_trend,
        df_trigger      = df_trigger,
        base_params     = base_params,
        best_row        = best_row,
        override_keys   = override_keys,
    )

    return ranked_df


# ─────────────────────────────────────────────
# TOP RESULTS PRINTER
# ─────────────────────────────────────────────
def _print_top_results(
    ranked_df: pd.DataFrame,
    symbol: str,
    top_n: int,
    override_keys: list
) -> None:
    """Print top N ranked combinations to terminal."""
    display_n = min(top_n, len(ranked_df))

    print(f"\n  TOP {display_n} COMBINATIONS  |  {symbol}")
    print(f"  {'─'*90}")

    metric_cols = [
        "rank", "total_trades", "profit_factor",
        "win_rate_pct", "total_pnl_pct_net",
        "total_pnl_usd_net", "total_pnl_inr_net",
        "max_drawdown_pct",
    ]
    display_cols = metric_cols + [
        k for k in override_keys if k in ranked_df.columns
    ]
    display_cols = [c for c in display_cols if c in ranked_df.columns]

    top_df = ranked_df[display_cols].head(display_n)

    # Format for readability
    fmt = top_df.copy()
    if "profit_factor"     in fmt.columns:
        fmt["profit_factor"]     = fmt["profit_factor"].map("{:.3f}".format)
    if "win_rate_pct"      in fmt.columns:
        fmt["win_rate_pct"]      = fmt["win_rate_pct"].map("{:.1f}%".format)
    if "total_pnl_pct_net" in fmt.columns:
        fmt["total_pnl_pct_net"] = fmt["total_pnl_pct_net"].map("{:.2f}%".format)
    if "total_pnl_usd_net" in fmt.columns:
        fmt["total_pnl_usd_net"] = fmt["total_pnl_usd_net"].map("${:.2f}".format)
    if "total_pnl_inr_net" in fmt.columns:
        fmt["total_pnl_inr_net"] = fmt["total_pnl_inr_net"].map("₹{:.2f}".format)
    if "max_drawdown_pct"  in fmt.columns:
        fmt["max_drawdown_pct"]  = fmt["max_drawdown_pct"].map("{:.2f}%".format)

    print(fmt.to_string(index=False))
    print()


# ─────────────────────────────────────────────
# BEST COMBO PERIODIC PnL
# ─────────────────────────────────────────────
def _print_best_combo_periodic(
    symbol: str,
    df_trend: pd.DataFrame,
    df_trigger: pd.DataFrame,
    base_params: dict,
    best_row: pd.Series,
    override_keys: list,
) -> None:
    """
    Re-run backtest with best params and print yearly/monthly PnL.
    Uses already-fetched DataFrames — no extra API call.
    """
    best_overrides = {
        k: best_row[k]
        for k in override_keys
        if k in best_row.index
    }

    params = deepcopy(base_params)
    params.update(best_overrides)

    try:
        trades   = run_backtest(symbol, df_trend.copy(), df_trigger.copy(), params)
        periodic = calculate_periodic_pnl(trades, symbol)
        print_periodic_pnl(periodic, symbol)
    except Exception as e:
        print(f"  [WARNING] Could not compute periodic PnL: {e}")


# ─────────────────────────────────────────────
# MULTI-SYMBOL OPTIMIZER
# ─────────────────────────────────────────────
def run_optimization(
    symbols: list             = None,
    base_params: dict         = None,
    optimization_ranges: dict = None,
    label: str                = "",
    min_trades: int           = 10,
    top_n: int                = 10,
) -> dict:
    """
    Run optimization across multiple symbols.

    Args:
        symbols             : List of symbols e.g. ['BTCUSD', 'ETHUSD']
                              Defaults to config.SYMBOLS if not provided
        base_params         : Base config dict.
                              Defaults to config.get_base_params() if not provided
        optimization_ranges : Dict of param -> list of values.
                              Defaults to config.OPTIMIZATION_RANGES if not provided
        label               : Optional label for file naming
        min_trades          : Minimum trades threshold for ranking
        top_n               : Top N results to print per symbol

    Returns:
        Dict of symbol -> ranked DataFrame
    """
    import time
    total_start = time.time()

    # ── Resolve defaults from config ──────────────────────────────
    if symbols is None:
        symbols = getattr(config, "SYMBOLS", ["BTCUSD"])

    if base_params is None:
        if hasattr(config, "get_base_params"):
            base_params = config.get_base_params()
        elif hasattr(config, "BASE_PARAMS"):
            base_params = deepcopy(config.BASE_PARAMS)
        else:
            raise ValueError(
                "base_params not provided and config has no "
                "get_base_params() or BASE_PARAMS."
            )

    if optimization_ranges is None:
        if hasattr(config, "OPTIMIZATION_RANGES"):
            optimization_ranges = config.OPTIMIZATION_RANGES
        else:
            raise ValueError(
                "optimization_ranges not provided and "
                "config has no OPTIMIZATION_RANGES."
            )

    print(
        f"\n{'='*70}\n"
        f"  OPTIMIZATION RUN\n"
        f"  Symbols    : {symbols}\n"
        f"  Params     : {list(optimization_ranges.keys())}\n"
        f"  Grid size  : {len(build_param_grid(optimization_ranges))} "
        f"combinations per symbol\n"
        f"  Min trades : {min_trades}\n"
        f"{'='*70}"
    )

    all_results = {}

    for symbol in symbols:
        try:
            ranked_df = optimize_symbol(
                symbol              = symbol,
                base_params         = base_params,
                optimization_ranges = optimization_ranges,
                label               = label,
                min_trades          = min_trades,
                top_n               = top_n,
            )
            all_results[symbol] = ranked_df

        except Exception as e:
            print(f"\n  [ERROR] {symbol}: {e}")
            traceback.print_exc()
            all_results[symbol] = pd.DataFrame()

    total_elapsed = time.time() - total_start
    print(
        f"\n{'='*70}\n"
        f"  OPTIMIZATION COMPLETE\n"
        f"  Total time : {_format_duration(total_elapsed)}\n"
        f"  Symbols    : {len(symbols)}\n"
        f"{'='*70}\n"
    )

    return all_results


# ─────────────────────────────────────────────
# LOAD BEST PARAMS FROM JSON
# ─────────────────────────────────────────────
def load_best_params(json_path: str) -> dict:
    """
    Load best params from a previously saved JSON file.
    Use this to apply optimizer results to a live backtest
    or signal generator run.

    Args:
        json_path : Path to best_params_*.json file

    Returns:
        Full params dict ready to pass to run_backtest()
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Best params file not found: {json_path}")

    with open(json_path, "r") as f:
        data = json.load(f)

    params = data.get("best_params", {})

    print(
        f"  [OPTIMIZER] Loaded best params from: {json_path}\n"
        f"  Symbol     : {data.get('symbol', 'unknown')}\n"
        f"  Optimized  : {data.get('optimized_at', 'unknown')}\n"
        f"  PF         : {data.get('rank_1_metrics', {}).get('profit_factor', 0):.3f}\n"
        f"  Net PnL %  : {data.get('rank_1_metrics', {}).get('total_pnl_pct_net', 0):.2f}%\n"
        f"  Net USD    : ${data.get('rank_1_metrics', {}).get('total_pnl_usd_net', 0):.2f}\n"
        f"  Net INR    : ₹{data.get('rank_1_metrics', {}).get('total_pnl_inr_net', 0):.2f}\n"
        f"  Keys opt.  : {data.get('optimized_keys', [])}"
    )

    return params


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":

    # ── Example optimization_ranges ───────────────────────────────
    # These override base_params for each combination.
    # All other params come from config.get_base_params().
    # Adjust ranges based on what you want to optimize.
    OPTIMIZATION_RANGES = getattr(
        config,
        "OPTIMIZATION_RANGES",
        {
            # ATR SL multiplier: how wide the stop loss is
            "atr_sl_multiplier"         : [1.0, 1.5, 2.0, 2.5],

            # ATR TP multiplier: how wide the take profit is
            "atr_tp_multiplier"         : [2.0, 3.0, 4.0, 5.0],

            # ADX threshold: minimum trend strength to enter
            "adx_min_threshold"         : [20, 25, 30],

            # EMA200 proximity: how close price must be to EMA200
            "ema200_proximity_atr_mult" : [0.5, 1.0, 1.5, 2.0],
        }
    )

    run_optimization(
        symbols             = getattr(config, "SYMBOLS", ["BTCUSD", "ETHUSD"]),
        optimization_ranges = OPTIMIZATION_RANGES,
        label               = "swing_4h_1h",
        min_trades          = 10,
        top_n               = 10,
    )
