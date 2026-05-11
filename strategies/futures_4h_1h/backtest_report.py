# =====================================================
# backtest_report.py
# Generates terminal + CSV + PNG summary report
# across all backtest runs (swing + intraday)
#
# FIXES APPLIED:
#   FIX1  - generate_full_report() added as the single
#           entry point called by run_backtest.py.
#           Calls print_full_report(), save_combined_csv(),
#           save_yearly_monthly_csv(), save_comparison_chart()
#           in sequence.
#
#   FIX2  - print_full_report() now shows total_pnl_usd,
#           total_pnl_inr, max_drawdown_usd in terminal table.
#           INR column added as required.
#
#   FIX3  - print_full_report() now prints yearly and monthly
#           PnL breakdown (USD + INR) per symbol per run.
#
#   FIX4  - save_combined_csv() now serialises yearly/monthly
#           dict fields using json.dumps() instead of Python
#           repr. Consistent with backtest_engine.save_metrics_csv().
#
#   FIX5  - save_comparison_chart() now shows total_pnl_usd
#           and max_drawdown_usd panels in addition to
#           profit_factor and win_rate_pct.
#
#   FIX6  - Column format strings widened to accommodate
#           USD ($12,345) and INR (Rs.1,034,580) values
#           without overflow or misalignment.
#
#   FIX7  - Cross-mode comparison section now includes
#           net_usd and net_inr columns.
#
#   FIX8  - save_yearly_monthly_csv() added as a dedicated
#           function that writes one row per symbol per
#           year/month. Cleaner than embedding dicts in
#           the combined CSV.
# =====================================================

import os
import json
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from datetime import datetime

RESULTS_DIR = "../../results"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _ensure_results_dir() -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)


def _timestamp_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _grade(profit_factor: float, win_rate: float) -> str:
    """
    Simple letter grade for quick visual assessment.
    Based on profit factor + win rate combined.
    """
    if profit_factor >= 2.0 and win_rate >= 55:
        return "A"
    if profit_factor >= 1.5 and win_rate >= 50:
        return "B"
    if profit_factor >= 1.2 and win_rate >= 45:
        return "C"
    if profit_factor >= 1.0:
        return "D"
    return "F"


def _add_bar_labels(ax, bars, fmt: str = "{:.2f}") -> None:
    """
    Add value labels on top of each bar in a bar chart.
    Positive values: label above bar.
    Negative values: label below bar.
    """
    for bar in bars:
        height = bar.get_height()
        if height == 0:
            continue
        va = "bottom" if height >= 0 else "top"
        y = (
            height + (abs(height) * 0.02)
            if height >= 0
            else height - (abs(height) * 0.02)
        )
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            y,
            fmt.format(height),
            ha="center",
            va=va,
            fontsize=7,
            fontweight="bold"
        )


# ─────────────────────────────────────────────
# TERMINAL REPORT
# ─────────────────────────────────────────────
def print_full_report(all_runs: list) -> None:
    """
    Print a structured terminal report for all runs.
    Each run = one mode (swing or intraday).

    FIX2: Added total_pnl_usd, total_pnl_inr, max_drawdown_usd
          columns to the per-symbol summary table.
    FIX3: Added yearly and monthly PnL breakdown per symbol.
    FIX6: Column widths widened for USD/INR values.
    FIX7: Cross-mode comparison now includes net_usd, net_inr.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\n{'#' * 90}")
    print(f"  DELTA EXCHANGE SIGNAL GENERATOR - BACKTEST REPORT")
    print(f"  Generated : {now}")
    print(f"{'#' * 90}")

    for run in all_runs:
        mode = run["mode"].upper()
        metrics = run["metrics"]

        print(f"\n{'=' * 90}")
        print(
            f"  MODE: {mode}  |  {run['trend_tf']} trend + "
            f"{run['trigger_tf']} trigger  |  "
            f"exit={run['exit_mode']}"
        )
        print(f"{'=' * 90}")

        if not metrics or all(m["total_trades"] == 0 for m in metrics):
            print("  No trades generated for this mode.")
            continue

        # ── Per-symbol summary table ──────────────────────────────
        # FIX6: widened columns for USD/INR
        col = (
            "{:<10} {:>7} {:>7} {:>6} "
            "{:>10} {:>12} {:>14} "
            "{:>12} {:>6}"
        )
        print(col.format(
            "SYMBOL", "TRADES", "WIN%", "PF",
            "NET PNL%", "NET USD", "NET INR",
            "MAX DD USD", "GRADE"
        ))
        print("-" * 90)

        for m in metrics:
            if m["total_trades"] == 0:
                print(col.format(
                    m["symbol"], 0, "-", "-",
                    "-", "-", "-", "-", "-"
                ))
                continue

            grade = _grade(m["profit_factor"], m["win_rate_pct"])
            print(col.format(
                m["symbol"],
                m["total_trades"],
                f"{m['win_rate_pct']:.1f}%",
                f"{m['profit_factor']:.2f}",
                f"{m['total_pnl_pct_net']:.2f}%",  # FIX2
                f"${m['total_pnl_usd']:,.0f}",  # FIX2
                f"Rs.{m['total_pnl_inr']:,.0f}",  # FIX2
                f"${m['max_drawdown_usd']:,.0f}",  # FIX2
                grade
            ))

        # ── Best performers for this mode ─────────────────────────
        valid = [m for m in metrics if m["total_trades"] > 0]
        if valid:
            best_pf = max(valid, key=lambda x: x["profit_factor"])
            best_win = max(valid, key=lambda x: x["win_rate_pct"])
            best_usd = max(valid, key=lambda x: x["total_pnl_usd"])

            print(
                f"\n  Best Profit Factor : "
                f"{best_pf['symbol']} "
                f"(PF={best_pf['profit_factor']:.2f})"
            )
            print(
                f"  Best Win Rate      : "
                f"{best_win['symbol']} "
                f"({best_win['win_rate_pct']:.1f}%)"
            )
            print(
                f"  Best Net USD PnL   : "
                f"{best_usd['symbol']} "
                f"(${best_usd['total_pnl_usd']:,.0f}  "
                f"Rs.{best_usd['total_pnl_inr']:,.0f})"
            )

        # ── Yearly PnL breakdown (FIX3) ───────────────────────────
        for m in metrics:
            yearly_usd = m.get("yearly_pnl_usd", {})
            yearly_inr = m.get("yearly_pnl_inr", {})
            if not yearly_usd:
                continue

            print(f"\n  Yearly PnL  |  {m['symbol']}")
            print(f"  {'Year':<8} {'Net USD':>12} {'Net INR':>14} {'Status':>8}")
            print(f"  {'-' * 46}")

            for year in sorted(yearly_usd.keys()):
                usd = yearly_usd.get(year, 0.0)
                inr = yearly_inr.get(year, 0.0)
                status = "PROFIT" if usd >= 0 else "LOSS"
                print(
                    f"  {year:<8} "
                    f"${usd:>10,.0f} "
                    f"Rs.{inr:>10,.0f} "
                    f"{status:>8}"
                )

        # ── Monthly PnL breakdown (FIX3) ──────────────────────────
        for m in metrics:
            monthly_usd = m.get("monthly_pnl_usd", {})
            monthly_inr = m.get("monthly_pnl_inr", {})
            if not monthly_usd:
                continue

            print(f"\n  Monthly PnL  |  {m['symbol']}")
            print(f"  {'Month':<10} {'Net USD':>12} {'Net INR':>14} {'Status':>8}")
            print(f"  {'-' * 48}")

            for month in sorted(monthly_usd.keys()):
                usd = monthly_usd.get(month, 0.0)
                inr = monthly_inr.get(month, 0.0)
                status = "PROFIT" if usd >= 0 else "LOSS"
                print(
                    f"  {month:<10} "
                    f"${usd:>10,.0f} "
                    f"Rs.{inr:>10,.0f} "
                    f"{status:>8}"
                )

    # ── Cross-mode comparison (FIX7) ──────────────────────────────
    if len(all_runs) >= 2:
        print(f"\n{'=' * 90}")
        print("  CROSS-MODE COMPARISON")
        print(f"{'=' * 90}")

        col2 = "{:<22} {:<10} {:>7} {:>7} {:>6} {:>12} {:>14}"
        print(col2.format(
            "LABEL", "SYMBOL", "TRADES", "WIN%", "PF",
            "NET USD", "NET INR"  # FIX7
        ))
        print("-" * 90)

        for run in all_runs:
            for m in run["metrics"]:
                if m["total_trades"] == 0:
                    continue
                print(col2.format(
                    run["label"],
                    m["symbol"],
                    m["total_trades"],
                    f"{m['win_rate_pct']:.1f}%",
                    f"{m['profit_factor']:.2f}",
                    f"${m['total_pnl_usd']:,.0f}",  # FIX7
                    f"Rs.{m['total_pnl_inr']:,.0f}"  # FIX7
                ))

    print(f"\n{'#' * 90}\n")


# ─────────────────────────────────────────────
# COMBINED CSV EXPORT
# ─────────────────────────────────────────────
def save_combined_csv(all_runs: list) -> str:
    """
    Save all metrics from all runs into one combined CSV.
    Adds mode, label, trend_tf, trigger_tf, exit_mode, grade columns.

    FIX4: yearly/monthly dict fields serialised with json.dumps()
          instead of Python repr. Consistent with
          backtest_engine.save_metrics_csv().

    Returns saved file path.
    """
    _ensure_results_dir()

    rows = []
    for run in all_runs:
        for m in run["metrics"]:
            row = {}

            # Scalar fields only — dicts handled separately below
            for k, v in m.items():
                if k not in (
                        "yearly_pnl_usd", "yearly_pnl_inr",
                        "monthly_pnl_usd", "monthly_pnl_inr"
                ):
                    row[k] = v

            # FIX4: serialise dicts as JSON strings
            row["yearly_pnl_usd"] = json.dumps(
                m.get("yearly_pnl_usd", {})
            )
            row["yearly_pnl_inr"] = json.dumps(
                m.get("yearly_pnl_inr", {})
            )
            row["monthly_pnl_usd"] = json.dumps(
                m.get("monthly_pnl_usd", {})
            )
            row["monthly_pnl_inr"] = json.dumps(
                m.get("monthly_pnl_inr", {})
            )

            # Run-level metadata
            row["mode"] = run["mode"]
            row["label"] = run["label"]
            row["trend_tf"] = run["trend_tf"]
            row["trigger_tf"] = run["trigger_tf"]
            row["exit_mode"] = run["exit_mode"]
            row["grade"] = _grade(
                m.get("profit_factor", 0),
                m.get("win_rate_pct", 0)
            )
            rows.append(row)

    if not rows:
        return ""

    df = pd.DataFrame(rows)

    # Reorder columns for readability
    priority_cols = [
        "mode", "label", "symbol", "trend_tf", "trigger_tf",
        "exit_mode", "total_trades", "win_rate_pct",
        "profit_factor",
        "total_pnl_pct", "total_pnl_pct_net",
        "total_pnl_usd", "total_pnl_inr",
        "max_drawdown_pct", "max_drawdown_usd",
        "avg_win_pct", "avg_loss_pct",
        "best_trade_pct", "worst_trade_pct", "avg_trade_pct",
        "total_trades_buy", "total_trades_sell",
        "win_streak_max", "loss_streak_max",
        "grade",
        "yearly_pnl_usd", "yearly_pnl_inr",
        "monthly_pnl_usd", "monthly_pnl_inr",
    ]
    existing = [c for c in priority_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in existing]
    df = df[existing + remaining]

    ts = _timestamp_str()
    filename = f"{RESULTS_DIR}/combined_report_{ts}.csv"
    df.to_csv(filename, index=False)
    print(f"  [REPORT] Combined CSV saved       : {filename}")
    return filename


# ─────────────────────────────────────────────
# YEARLY / MONTHLY CSV EXPORT  (FIX8)
# ─────────────────────────────────────────────
def save_yearly_monthly_csv(all_runs: list) -> tuple:
    """
    FIX8: Write dedicated yearly and monthly PnL CSVs.
    One row per symbol per year / per symbol per month.
    Much cleaner than embedding JSON dicts in combined CSV.

    Returns (yearly_path, monthly_path).
    """
    _ensure_results_dir()
    ts = _timestamp_str()

    # ── Yearly CSV ────────────────────────────────────────────────
    yearly_rows = []
    for run in all_runs:
        for m in run["metrics"]:
            yearly_usd = m.get("yearly_pnl_usd", {})
            yearly_inr = m.get("yearly_pnl_inr", {})
            for year in sorted(yearly_usd.keys()):
                usd = yearly_usd.get(year, 0.0)
                inr = yearly_inr.get(year, 0.0)
                yearly_rows.append({
                    "mode": run["mode"],
                    "label": run["label"],
                    "symbol": m["symbol"],
                    "trend_tf": run["trend_tf"],
                    "trigger_tf": run["trigger_tf"],
                    "year": year,
                    "pnl_usd": round(usd, 2),
                    "pnl_inr": round(inr, 2),
                    "status": "PROFIT" if usd >= 0 else "LOSS",
                })

    yearly_path = ""
    if yearly_rows:
        df_y = pd.DataFrame(yearly_rows)
        yearly_path = f"{RESULTS_DIR}/yearly_pnl_{ts}.csv"
        df_y.to_csv(yearly_path, index=False)
        print(f"  [REPORT] Yearly PnL CSV saved     : {yearly_path}")

    # ── Monthly CSV ───────────────────────────────────────────────
    monthly_rows = []
    for run in all_runs:
        for m in run["metrics"]:
            monthly_usd = m.get("monthly_pnl_usd", {})
            monthly_inr = m.get("monthly_pnl_inr", {})
            for month in sorted(monthly_usd.keys()):
                usd = monthly_usd.get(month, 0.0)
                inr = monthly_inr.get(month, 0.0)
                monthly_rows.append({
                    "mode": run["mode"],
                    "label": run["label"],
                    "symbol": m["symbol"],
                    "trend_tf": run["trend_tf"],
                    "trigger_tf": run["trigger_tf"],
                    "month": month,
                    "pnl_usd": round(usd, 2),
                    "pnl_inr": round(inr, 2),
                    "status": "PROFIT" if usd >= 0 else "LOSS",
                })

    monthly_path = ""
    if monthly_rows:
        df_m = pd.DataFrame(monthly_rows)
        monthly_path = f"{RESULTS_DIR}/monthly_pnl_{ts}.csv"
        df_m.to_csv(monthly_path, index=False)
        print(f"  [REPORT] Monthly PnL CSV saved    : {monthly_path}")

    return yearly_path, monthly_path


# ─────────────────────────────────────────────
# COMPARISON CHART
# ─────────────────────────────────────────────
def save_comparison_chart(all_runs: list) -> str:
    """
    Save a multi-panel comparison chart PNG.

    FIX5: Four panels now show:
      Panel 1: Profit Factor
      Panel 2: Win Rate %
      Panel 3: Net PnL USD  (was total_pnl_pct)
      Panel 4: Max Drawdown USD  (was max_drawdown_pct)

    USD values are more meaningful for 100-lot positions
    on BTC/ETH than raw percentage moves.

    Returns saved file path.
    """
    _ensure_results_dir()

    # Flatten all metrics with labels
    labels = []
    pf_vals = []
    wr_vals = []
    usd_vals = []
    dd_vals = []

    for run in all_runs:
        for m in run["metrics"]:
            if m["total_trades"] == 0:
                continue
            lbl = f"{m['symbol']}\n{run['label']}"
            labels.append(lbl)
            pf_vals.append(m.get("profit_factor", 0.0))
            wr_vals.append(m.get("win_rate_pct", 0.0))
            usd_vals.append(m.get("total_pnl_usd", 0.0))  # FIX5
            dd_vals.append(m.get("max_drawdown_usd", 0.0))  # FIX5

    if not labels:
        return ""

    x = np.arange(len(labels))
    width = 0.6

    fig = plt.figure(figsize=(max(12, len(labels) * 2.5), 14))
    fig.suptitle(
        "Backtest Comparison Report  |  Delta Exchange Signal Generator",
        fontsize=13, fontweight="bold", y=0.98
    )

    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    # ── Panel 1: Profit Factor ─────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    colors_pf = [
        "#4CAF50" if v >= 1.5
        else "#FF9800" if v >= 1.0
        else "#F44336"
        for v in pf_vals
    ]
    bars1 = ax1.bar(x, pf_vals, width, color=colors_pf, alpha=0.85)
    ax1.axhline(1.0, color="red", linewidth=1.0, linestyle="--",
                label="Break-even (1.0)")
    ax1.axhline(1.5, color="orange", linewidth=1.0, linestyle="--",
                label="Good (1.5)")
    ax1.axhline(2.0, color="green", linewidth=1.0, linestyle="--",
                label="Excellent (2.0)")
    ax1.set_title("Profit Factor", fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, fontsize=8)
    ax1.legend(fontsize=7)
    ax1.grid(True, alpha=0.3, axis="y")
    _add_bar_labels(ax1, bars1, fmt="{:.2f}")

    # ── Panel 2: Win Rate % ────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    colors_wr = [
        "#4CAF50" if v >= 55
        else "#FF9800" if v >= 45
        else "#F44336"
        for v in wr_vals
    ]
    bars2 = ax2.bar(x, wr_vals, width, color=colors_wr, alpha=0.85)
    ax2.axhline(50, color="gray", linewidth=1.0, linestyle="--",
                label="50% line")
    ax2.axhline(55, color="green", linewidth=1.0, linestyle="--",
                label="Good (55%)")
    ax2.set_title("Win Rate %", fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, fontsize=8)
    ax2.set_ylim(0, 100)
    ax2.legend(fontsize=7)
    ax2.grid(True, alpha=0.3, axis="y")
    _add_bar_labels(ax2, bars2, fmt="{:.1f}%")

    # ── Panel 3: Net PnL USD (FIX5) ───────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    colors_usd = [
        "#4CAF50" if v > 0 else "#F44336"
        for v in usd_vals
    ]
    bars3 = ax3.bar(x, usd_vals, width, color=colors_usd, alpha=0.85)
    ax3.axhline(0, color="gray", linewidth=1.0, linestyle="--")
    ax3.set_title("Net PnL USD (after fees)", fontweight="bold")  # FIX5
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels, fontsize=8)

