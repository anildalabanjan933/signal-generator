# =====================================================
# run_backtest.py
# Entry point for running the swing backtest
#
# Usage:
#   python run_backtest.py --mode swing
#
# What it does:
#   1. Reads symbols from config.SYMBOLS
#   2. Builds per-symbol params via config.build_params()
#   3. Calls backtest_engine.run_backtest_all_symbols()
#   4. Prints yearly/monthly PnL reports
#   5. Saves equity curve PNGs and trade CSVs to ./results/
# =====================================================
import argparse
import os
import sys

# Add project root to Python path
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
)

from strategies.futures_2h_30m import config
from strategies.futures_2h_30m.backtest import run_backtest_all_symbols

# ─────────────────────────────────────────────
# YEARLY REPORT
# ─────────────────────────────────────────────
def print_yearly_report(metrics_list: list) -> None:
    valid = [m for m in metrics_list if m["total_trades"] > 0]
    if not valid:
        return

    print(f"\n{'='*80}")
    print(f"  YEARLY PnL REPORT")
    print(f"{'='*80}")

    for m in valid:
        symbol     = m["symbol"]
        yearly_usd = m.get("yearly_pnl_usd", {})
        yearly_inr = m.get("yearly_pnl_inr", {})

        if not yearly_usd:
            continue

        print(f"\n  {symbol}")
        print(f"  {'Year':<8} {'PnL USD':>14} {'PnL INR':>16}")
        print(f"  {'-'*40}")

        for yr in sorted(yearly_usd.keys()):
            usd = yearly_usd[yr]
            inr = yearly_inr.get(yr, 0.0)
            print(f"  {yr:<8} ${usd:>13,.2f} Rs.{inr:>13,.2f}")


# ─────────────────────────────────────────────
# MONTHLY REPORT
# ─────────────────────────────────────────────
def print_monthly_report(metrics_list: list) -> None:
    valid = [m for m in metrics_list if m["total_trades"] > 0]
    if not valid:
        return

    print(f"\n{'='*80}")
    print(f"  MONTHLY PnL REPORT")
    print(f"{'='*80}")

    for m in valid:
        symbol      = m["symbol"]
        monthly_usd = m.get("monthly_pnl_usd", {})
        monthly_inr = m.get("monthly_pnl_inr", {})

        if not monthly_usd:
            continue

        print(f"\n  {symbol}")
        print(f"  {'Month':<12} {'PnL USD':>14} {'PnL INR':>16}")
        print(f"  {'-'*44}")

        for key in sorted(monthly_usd.keys()):
            usd = monthly_usd[key]
            inr = monthly_inr.get(key, 0.0)
            print(f"  {key:<12} ${usd:>13,.2f} Rs.{inr:>13,.2f}")


# ─────────────────────────────────────────────
# SWING MODE
# ─────────────────────────────────────────────
def run_swing(symbols: list) -> None:
    """
    Build per-symbol params and run the swing backtest.
    """
    # Validate symbols have config entries
    missing = [
        s for s in symbols
        if s not in config.LOT_SIZES or s not in config.CONTRACT_VALUES
    ]
    if missing:
        print(
            f"\n  [ERROR] These symbols are missing from config.LOT_SIZES "
            f"or config.CONTRACT_VALUES:\n    {missing}\n"
            f"  Add them to config.py before running."
        )
        sys.exit(1)

    # Build per-symbol params dict (E1 requirement)
    params_map = {
        symbol: config.build_params(symbol=symbol)
        for symbol in symbols
    }

    # Run backtest across all symbols — positional call avoids
    # keyword name mismatch between run_backtest.py and backtest_engine.py
    metrics_list = run_backtest_all_symbols(
        symbols,
        params_map,
        "swing"
    )

    # Print yearly and monthly PnL breakdowns
    print_yearly_report(metrics_list)
    print_monthly_report(metrics_list)

    # Final portfolio summary
    total_pnl_pct = sum(m.get("total_pnl_pct_net", 0) for m in metrics_list)
    total_trades  = sum(m.get("total_trades", 0) for m in metrics_list)

    print(f"\n{'='*80}")
    print(f"  PORTFOLIO TOTAL")
    print(f"{'='*80}")
    print(f"  Total Trades     : {total_trades}")
    print(f"  Total Net PnL %  : {total_pnl_pct:>10.2f}%")
    print(f"{'='*80}\n")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    os.makedirs("results", exist_ok=True)

    parser = argparse.ArgumentParser(
        description="Delta Exchange Swing Backtest Runner"
    )
    parser.add_argument(
        "--mode",
        type    = str,
        default = "swing",
        choices = ["swing"],
        help    = "Backtest mode (default: swing)"
    )
    parser.add_argument(
        "--symbols",
        type    = str,
        default = None,
        help    = "Comma-separated symbols to backtest. "
                  "Default: all symbols in config.SYMBOLS. "
                  "Example: --symbols BTCUSD,ETHUSD"
    )

    args = parser.parse_args()

    # Resolve symbol list
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = list(config.SYMBOLS)

    if not symbols:
        print("  [ERROR] No symbols found. Check config.SYMBOLS or --symbols argument.")
        sys.exit(1)

    print(f"\n  [RUN] mode={args.mode}  symbols={symbols}  days={config.BACKTEST_DAYS}")

    if args.mode == "swing":
        run_swing(symbols)


if __name__ == "__main__":
    main()
