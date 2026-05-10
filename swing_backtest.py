# =================================================
# swing_backtest.py - Full Backtest Engine
# MTF Swing Strategy: 4H Trend + 1H Entry
# Supertrend Flip Exit
#
# Reports:
#   - Trade log
#   - Yearly PnL (USD + INR)
#   - Monthly PnL (USD + INR)
#   - Equity curve chart
#   - PF, Max DD, Win Rate, Trade Count
# =================================================

import time
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

warnings.filterwarnings("ignore")

# Local modules
from config import (
    SYMBOLS, BACKTEST_DAYS, USD_TO_INR,
    TREND_TF, ENTRY_TF,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_LEVEL,
    ADX_PERIOD, ADX_THRESHOLD,
    SUPERTREND_ATR_PERIOD, SUPERTREND_MULTIPLIER,
    COMMISSION_MODE
)
from data_fetcher  import fetch_candles_by_days
from indicators    import add_indicators
from filters       import get_4h_trend, align_4h_trend_to_1h
from signal_engine import generate_signals

# -------------------------------------------------
# INDICATOR CONFIG DICT (passed to add_indicators)
# -------------------------------------------------
INDICATOR_CONFIG = {
    "EMA_FAST":               EMA_FAST,
    "EMA_SLOW":               EMA_SLOW,
    "RSI_PERIOD":             RSI_PERIOD,
    "ADX_PERIOD":             ADX_PERIOD,
    "SUPERTREND_ATR_PERIOD":  SUPERTREND_ATR_PERIOD,
    "SUPERTREND_MULTIPLIER":  SUPERTREND_MULTIPLIER,
}


# =================================================
# STEP 1: DATA PREPARATION
# =================================================
def prepare_data(symbol: str):
    """
    Fetch 4H and 1H candles, apply indicators.

    Returns:
        (df_4h, df_1h) with indicators applied
        or (None, None) on failure
    """
    print(f"\n{'='*55}")
    print(f"  Preparing data for {symbol}")
    print(f"{'='*55}")

    # Fetch extra days for indicator warmup (EMA200 needs ~200 candles)
    # 4H: 200 candles = 200 * 4h = 800h = ~34 days warmup
    # 1H: 200 candles = 200h = ~9 days warmup
    # Add 60 days buffer to be safe
    fetch_days = BACKTEST_DAYS + 60

    print(f"  Fetching {TREND_TF} candles ({fetch_days} days)...")
    df_4h = fetch_candles_by_days(symbol, TREND_TF, fetch_days)

    print(f"  Fetching {ENTRY_TF} candles ({fetch_days} days)...")
    df_1h = fetch_candles_by_days(symbol, ENTRY_TF, fetch_days)

    if df_4h.empty or df_1h.empty:
        print(f"  [ERROR] Failed to fetch data for {symbol}.")
        return None, None

    # Set datetime as index for alignment
    df_4h = df_4h.set_index("datetime")
    df_1h = df_1h.set_index("datetime")

    # Apply indicators
    print(f"  Applying indicators...")
    df_4h = add_indicators(df_4h, INDICATOR_CONFIG)
    df_1h = add_indicators(df_1h, INDICATOR_CONFIG)

    # Trim to actual backtest period (last BACKTEST_DAYS days)
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=BACKTEST_DAYS)
    df_4h  = df_4h[df_4h.index >= cutoff]
    df_1h  = df_1h[df_1h.index >= cutoff]

    print(f"  4H candles in backtest window : {len(df_4h)}")
    print(f"  1H candles in backtest window : {len(df_1h)}")

    return df_4h, df_1h


# =================================================
# STEP 2: RUN BACKTEST
# =================================================
def run_backtest(symbol: str, df_4h: pd.DataFrame, df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Execute the backtest simulation.

    Logic:
        - Walk through each 1H candle in order
        - Check 4H trend filter (forward-filled)
        - Check 1H entry conditions
        - Track open position
        - Exit on Supertrend flip
        - Record each completed trade

    Args:
        symbol : Trading symbol
        df_4h  : 4H DataFrame with indicators
        df_1h  : 1H DataFrame with indicators

    Returns:
        DataFrame of completed trades with PnL
    """
    cfg        = SYMBOLS[symbol]
    lots       = cfg["lots"]
    cv         = cfg["contract_value"]   # BTC or ETH per lot
    commission = cfg["taker_commission_rate"] if COMMISSION_MODE == "taker" else cfg["maker_commission_rate"]

    # --- Align 4H trend to 1H ---
    trend_4h      = get_4h_trend(df_4h, ADX_THRESHOLD)
    trend_aligned = align_4h_trend_to_1h(trend_4h, df_1h)

    # --- Generate signals ---
    df_signals = generate_signals(df_1h, trend_aligned)

    # --- Simulation ---
    trades        = []
    position      = None   # None or dict with trade details
    position_side = None   # 'buy' or 'sell'

    for i in range(1, len(df_signals)):
        row      = df_signals.iloc[i]
        candle_t = df_signals.index[i]
        price    = row["close"]

        # --- EXIT LOGIC (check before entry) ---
        if position is not None:
            should_exit = False

            if position_side == "buy"  and row["exit_signal"] == "exit_buy":
                should_exit = True
            if position_side == "sell" and row["exit_signal"] == "exit_sell":
                should_exit = True

            if should_exit:
                entry_price = position["entry_price"]
                exit_price  = price
                qty_crypto  = lots * cv   # Actual crypto quantity

                # PnL calculation (USD)
                if position_side == "buy":
                    raw_pnl = (exit_price - entry_price) * qty_crypto
                else:
                    raw_pnl = (entry_price - exit_price) * qty_crypto

                # Commission: entry + exit (both taker)
                notional   = entry_price * qty_crypto
                commission_cost = 2 * commission * notional

                net_pnl_usd = raw_pnl - commission_cost
                net_pnl_inr = net_pnl_usd * USD_TO_INR

                trades.append({
                    "symbol":        symbol,
                    "side":          position_side,
                    "entry_time":    position["entry_time"],
                    "exit_time":     candle_t,
                    "entry_price":   entry_price,
                    "exit_price":    exit_price,
                    "lots":          lots,
                    "qty_crypto":    qty_crypto,
                    "raw_pnl_usd":   raw_pnl,
                    "commission_usd":commission_cost,
                    "net_pnl_usd":   net_pnl_usd,
                    "net_pnl_inr":   net_pnl_inr,
                    "duration_hrs":  (candle_t - position["entry_time"]).total_seconds() / 3600,
                })

                position      = None
                position_side = None

        # --- ENTRY LOGIC (only if no open position) ---
        if position is None:
            if row["signal"] == "buy":
                position      = {"entry_price": price, "entry_time": candle_t}
                position_side = "buy"

            elif row["signal"] == "sell":
                position      = {"entry_price": price, "entry_time": candle_t}
                position_side = "sell"

    # --- Close any open position at last candle ---
    if position is not None:
        last_row   = df_signals.iloc[-1]
        exit_price = last_row["close"]
        candle_t   = df_signals.index[-1]
        qty_crypto = lots * cv

        if position_side == "buy":
            raw_pnl = (exit_price - position["entry_price"]) * qty_crypto
        else:
            raw_pnl = (position["entry_price"] - exit_price) * qty_crypto

        notional        = position["entry_price"] * qty_crypto
        commission_cost = 2 * commission * notional
        net_pnl_usd     = raw_pnl - commission_cost
        net_pnl_inr     = net_pnl_usd * USD_TO_INR

        trades.append({
            "symbol":         symbol,
            "side":           position_side,
            "entry_time":     position["entry_time"],
            "exit_time":      candle_t,
            "entry_price":    position["entry_price"],
            "exit_price":     exit_price,
            "lots":           lots,
            "qty_crypto":     qty_crypto,
            "raw_pnl_usd":    raw_pnl,
            "commission_usd": commission_cost,
            "net_pnl_usd":    net_pnl_usd,
            "net_pnl_inr":    net_pnl_inr,
            "duration_hrs":   (candle_t - position["entry_time"]).total_seconds() / 3600,
        })

    df_trades = pd.DataFrame(trades)
    if not df_trades.empty:
        df_trades["exit_time"]  = pd.to_datetime(df_trades["exit_time"],  utc=True)
        df_trades["entry_time"] = pd.to_datetime(df_trades["entry_time"], utc=True)

    return df_trades


# =================================================
# STEP 3: EQUITY CURVE
# =================================================
def build_equity_curve(df_trades: pd.DataFrame, starting_equity: float = 0.0) -> pd.Series:
    """
    Build cumulative equity curve from trade PnL.

    Args:
        df_trades       : Completed trades DataFrame
        starting_equity : Starting equity in USD (default 0)

    Returns:
        pd.Series of cumulative PnL indexed by exit_time
    """
    if df_trades.empty:
        return pd.Series(dtype=float)

    equity = df_trades.set_index("exit_time")["net_pnl_usd"].cumsum() + starting_equity
    return equity


# =================================================
# STEP 4: PERFORMANCE METRICS
# =================================================
def calculate_metrics(df_trades: pd.DataFrame, equity: pd.Series) -> dict:
    """
    Calculate full performance metrics.

    Args:
        df_trades : Completed trades DataFrame
        equity    : Cumulative equity curve

    Returns:
        Dict of performance metrics
    """
    if df_trades.empty:
        return {}

    pnl         = df_trades["net_pnl_usd"]
    winners     = pnl[pnl > 0]
    losers      = pnl[pnl < 0]

    total_trades = len(df_trades)
    win_count    = len(winners)
    loss_count   = len(losers)
    win_rate     = (win_count / total_trades * 100) if total_trades > 0 else 0

    gross_profit = winners.sum() if not winners.empty else 0
    gross_loss   = abs(losers.sum()) if not losers.empty else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    total_pnl_usd = pnl.sum()
    total_pnl_inr = total_pnl_usd * USD_TO_INR

    avg_win  = winners.mean() if not winners.empty else 0
    avg_loss = losers.mean()  if not losers.empty  else 0
    avg_rr   = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    # Max Drawdown
    if not equity.empty:
        rolling_max = equity.cummax()
        drawdown    = equity - rolling_max
        max_dd_usd  = drawdown.min()
        max_dd_inr  = max_dd_usd * USD_TO_INR
        max_dd_pct  = (max_dd_usd / rolling_max[drawdown.idxmin()] * 100) if rolling_max[drawdown.idxmin()] != 0 else 0
    else:
        max_dd_usd = max_dd_inr = max_dd_pct = 0

    avg_duration = df_trades["duration_hrs"].mean() if "duration_hrs" in df_trades.columns else 0

    return {
        "total_trades":   total_trades,
        "win_count":      win_count,
        "loss_count":     loss_count,
        "win_rate":       win_rate,
        "profit_factor":  profit_factor,
        "total_pnl_usd":  total_pnl_usd,
        "total_pnl_inr":  total_pnl_inr,
        "gross_profit":   gross_profit,
        "gross_loss":     gross_loss,
        "avg_win_usd":    avg_win,
        "avg_loss_usd":   avg_loss,
        "avg_rr":         avg_rr,
        "max_dd_usd":     max_dd_usd,
        "max_dd_inr":     max_dd_inr,
        "max_dd_pct":     max_dd_pct,
        "avg_duration_hrs": avg_duration,
    }


# =================================================
# STEP 5: PRINT REPORTS
# =================================================
def print_summary(symbol: str, df_trades: pd.DataFrame, equity: pd.Series) -> None:
    """Print overall performance summary."""
    m = calculate_metrics(df_trades, equity)
    if not m:
        print(f"\n  No trades found for {symbol}.")
        return

    print(f"\n{'='*55}")
    print(f"  SUMMARY : {symbol}")
    print(f"{'='*55}")
    print(f"  Total Trades     : {m['total_trades']}")
    print(f"  Win / Loss       : {m['win_count']} / {m['loss_count']}")
    print(f"  Win Rate         : {m['win_rate']:.1f}%")
    print(f"  Profit Factor    : {m['profit_factor']:.2f}")
    print(f"  Total PnL (USD)  : ${m['total_pnl_usd']:>12,.2f}")
    print(f"  Total PnL (INR)  : ₹{m['total_pnl_inr']:>12,.2f}")
    print(f"  Gross Profit     : ${m['gross_profit']:>12,.2f}")
    print(f"  Gross Loss       : ${m['gross_loss']:>12,.2f}")
    print(f"  Avg Win (USD)    : ${m['avg_win_usd']:>12,.2f}")
    print(f"  Avg Loss (USD)   : ${m['avg_loss_usd']:>12,.2f}")
    print(f"  Avg R:R          : {m['avg_rr']:.2f}")
    print(f"  Max Drawdown     : ${m['max_dd_usd']:>12,.2f}  ({m['max_dd_pct']:.1f}%)")
    print(f"  Max DD (INR)     : ₹{m['max_dd_inr']:>12,.2f}")
    print(f"  Avg Duration     : {m['avg_duration_hrs']:.1f} hrs")


def print_yearly_report(symbol: str, df_trades: pd.DataFrame) -> None:
    """Print yearly PnL breakdown."""
    if df_trades.empty:
        return

    print(f"\n{'='*55}")
    print(f"  YEARLY REPORT : {symbol}")
    print(f"{'='*55}")
    print(f"  {'Year':<8} {'Trades':>8} {'Win%':>8} {'PnL USD':>14} {'PnL INR':>16}")
    print(f"  {'-'*54}")

    df_trades["year"] = df_trades["exit_time"].dt.year

    for year, grp in df_trades.groupby("year"):
        pnl_usd  = grp["net_pnl_usd"].sum()
        pnl_inr  = pnl_usd * USD_TO_INR
        trades   = len(grp)
        wins     = len(grp[grp["net_pnl_usd"] > 0])
        win_rate = wins / trades * 100 if trades > 0 else 0
        print(f"  {year:<8} {trades:>8} {win_rate:>7.1f}% {pnl_usd:>14,.2f} {pnl_inr:>16,.2f}")


def print_monthly_report(symbol: str, df_trades: pd.DataFrame) -> None:
    """Print monthly PnL breakdown."""
    if df_trades.empty:
        return

    print(f"\n{'='*55}")
    print(f"  MONTHLY REPORT : {symbol}")
    print(f"{'='*55}")
    print(f"  {'Month':<12} {'Trades':>8} {'Win%':>8} {'PnL USD':>14} {'PnL INR':>16}")
    print(f"  {'-'*58}")

    df_trades["year_month"] = df_trades["exit_time"].dt.to_period("M")

    for ym, grp in df_trades.groupby("year_month"):
        pnl_usd  = grp["net_pnl_usd"].sum()
        pnl_inr  = pnl_usd * USD_TO_INR
        trades   = len(grp)
        wins     = len(grp[grp["net_pnl_usd"] > 0])
        win_rate = wins / trades * 100 if trades > 0 else 0
        print(f"  {str(ym):<12} {trades:>8} {win_rate:>7.1f}% {pnl_usd:>14,.2f} {pnl_inr:>16,.2f}")


# =================================================
# STEP 6: EQUITY CURVE CHART
# =================================================
def plot_equity_curves(results: dict) -> None:
    """
    Plot equity curves for all symbols + combined portfolio.

    Args:
        results : Dict of {symbol: (df_trades, equity)}
    """
    valid = {s: v for s, v in results.items() if not v[1].empty}
    if not valid:
        print("\n[WARNING] No equity data to plot.")
        return

    n_plots = len(valid) + 1  # individual + combined
    fig     = plt.figure(figsize=(16, 5 * n_plots))
    gs      = GridSpec(n_plots, 1, figure=fig, hspace=0.45)

    combined_pnl = None

    for i, (symbol, (df_trades, equity)) in enumerate(valid.items()):
        ax = fig.add_subplot(gs[i])
        ax.plot(equity.index, equity.values, linewidth=1.8, color="#2196F3", label=symbol)
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
        ax.fill_between(equity.index, equity.values, 0,
                        where=(equity.values >= 0), alpha=0.15, color="#4CAF50")
        ax.fill_between(equity.index, equity.values, 0,
                        where=(equity.values < 0),  alpha=0.15, color="#F44336")

        # Drawdown shading
        rolling_max = equity.cummax()
        drawdown    = equity - rolling_max
        ax2         = ax.twinx()
        ax2.fill_between(drawdown.index, drawdown.values, 0,
                         alpha=0.2, color="#FF5722", label="Drawdown")
        ax2.set_ylabel("Drawdown (USD)", color="#FF5722", fontsize=9)
        ax2.tick_params(axis="y", labelcolor="#FF5722")

        m = calculate_metrics(df_trades, equity)
        title = (f"{symbol} | Trades: {m['total_trades']} | "
                 f"Win: {m['win_rate']:.1f}% | PF: {m['profit_factor']:.2f} | "
                 f"PnL: ${m['total_pnl_usd']:,.0f} (₹{m['total_pnl_inr']:,.0f}) | "
                 f"MaxDD: {m['max_dd_pct']:.1f}%")
        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_ylabel("Cumulative PnL (USD)", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)

        # Accumulate combined
        if combined_pnl is None:
            combined_pnl = equity.copy()
        else:
            combined_pnl = combined_pnl.add(equity, fill_value=0)

    # Combined portfolio chart
    if combined_pnl is not None and not combined_pnl.empty:
        ax = fig.add_subplot(gs[n_plots - 1])
        ax.plot(combined_pnl.index, combined_pnl.values,
                linewidth=2.0, color="#9C27B0", label="Portfolio Combined")
        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
        ax.fill_between(combined_pnl.index, combined_pnl.values, 0,
                        where=(combined_pnl.values >= 0), alpha=0.15, color="#4CAF50")
        ax.fill_between(combined_pnl.index, combined_pnl.values, 0,
                        where=(combined_pnl.values < 0),  alpha=0.15, color="#F44336")

        rolling_max = combined_pnl.cummax()
        drawdown    = combined_pnl - rolling_max
        ax2         = ax.twinx()
        ax2.fill_between(drawdown.index, drawdown.values, 0,
                         alpha=0.2, color="#FF5722")
        ax2.set_ylabel("Drawdown (USD)", color="#FF5722", fontsize=9)
        ax2.tick_params(axis="y", labelcolor="#FF5722")

        total_pnl_usd = combined_pnl.iloc[-1] if not combined_pnl.empty else 0
        total_pnl_inr = total_pnl_usd * USD_TO_INR
        rolling_max_c = combined_pnl.cummax()
        dd_c          = combined_pnl - rolling_max_c
        max_dd_c      = dd_c.min()
        max_dd_pct_c  = (max_dd_c / rolling_max_c[dd_c.idxmin()] * 100) if rolling_max_c[dd_c.idxmin()] != 0 else 0

        ax.set_title(
            f"PORTFOLIO COMBINED | PnL: ${total_pnl_usd:,.0f} (₹{total_pnl_inr:,.0f}) | "
            f"MaxDD: {max_dd_pct_c:.1f}%",
            fontsize=10, fontweight="bold"
        )
        ax.set_ylabel("Cumulative PnL (USD)", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
        ax.legend(loc="upper left", fontsize=9)
        ax.grid(True, alpha=0.3)

    plt.suptitle(
        "MTF Swing Strategy Backtest | 4H Trend + 1H Entry | Supertrend Flip Exit",
        fontsize=13, fontweight="bold", y=1.01
    )
    plt.savefig("results/equity_curve.png", dpi=150, bbox_inches="tight")
    plt.show()
    print("\n[INFO] Equity curve saved to results/equity_curve.png")


# =================================================
# MAIN
# =================================================
def main():
    import os
    os.makedirs("results", exist_ok=True)

    print("\n" + "="*55)
    print("  MTF SWING BACKTEST - Delta Exchange")
    print(f"  Period  : {BACKTEST_DAYS} days (2 years)")
    print(f"  Symbols : {list(SYMBOLS.keys())}")
    print(f"  Trend TF: {TREND_TF} | Entry TF: {ENTRY_TF}")
    print(f"  INR Rate: {USD_TO_INR}")
    print("="*55)

    results = {}

    for symbol in SYMBOLS:
        # --- Fetch & prepare data ---
        df_4h, df_1h = prepare_data(symbol)
        if df_4h is None or df_1h is None:
            continue

        # --- Run backtest ---
        df_trades = run_backtest(symbol, df_4h, df_1h)
        equity    = build_equity_curve(df_trades)

        # --- Print reports ---
        print_summary(symbol, df_trades, equity)
        print_yearly_report(symbol, df_trades)
        print_monthly_report(symbol, df_trades)

        results[symbol] = (df_trades, equity)

        # --- Save trade log ---
        if not df_trades.empty:
            out_path = f"results/{symbol}_trades.csv"
            df_trades.to_csv(out_path, index=False)
            print(f"\n  [INFO] Trade log saved to {out_path}")

    # --- Combined portfolio summary ---
    all_trades_list = [v[0] for v in results.values() if not v[0].empty]
    if all_trades_list:
        all_trades = pd.concat(all_trades_list, ignore_index=True)
        all_trades = all_trades.sort_values("exit_time")
        combined_equity = build_equity_curve(all_trades)

        print_summary("PORTFOLIO COMBINED", all_trades, combined_equity)
        print_yearly_report("PORTFOLIO COMBINED", all_trades)
        print_monthly_report("PORTFOLIO COMBINED", all_trades)

    # --- Charts ---
    plot_equity_curves(results)


if __name__ == "__main__":
    main()
