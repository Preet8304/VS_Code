"""Run the XAUUSD scalping backtest over a date range and print a report.

Usage:
    python3 run_backtest.py --start 2012-05-15 --end 2018-12-31 --label in_sample
    python3 run_backtest.py --start 2019-01-01 --end 2022-03-04 --label out_of_sample
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from backtest import CostModel, RiskModel, run_backtest
from data_loader import load_h1, load_m15
from metrics import summarize, trades_to_frame, yearly_breakdown
from strategy import StrategyParams, generate_signals

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--label", default="full")
    p.add_argument("--initial-equity", type=float, default=10_000.0)
    p.add_argument("--risk-per-trade", type=float, default=0.005)
    p.add_argument("--spread", type=float, default=0.35)
    p.add_argument("--slippage", type=float, default=0.05)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    RESULTS_DIR.mkdir(exist_ok=True)

    m15 = load_m15()
    h1 = load_h1()

    if args.start:
        m15 = m15[m15["time"] >= pd.Timestamp(args.start)]
    if args.end:
        m15 = m15[m15["time"] <= pd.Timestamp(args.end)]
    m15 = m15.reset_index(drop=True)

    params = StrategyParams()
    signals = generate_signals(m15, h1, params)

    costs = CostModel(spread=args.spread, stop_slippage=args.slippage)
    risk = RiskModel(initial_equity=args.initial_equity, risk_per_trade=args.risk_per_trade)
    trades, equity_curve = run_backtest(signals, params, costs, risk)

    stats = summarize(trades, equity_curve, risk.initial_equity)
    yearly = yearly_breakdown(trades, risk.initial_equity)

    print(f"\n=== {args.label} | {m15['time'].iloc[0].date()} -> {m15['time'].iloc[-1].date()} ===")
    for k, v in stats.items():
        if isinstance(v, float):
            print(f"{k:>20}: {v:,.4f}")
        else:
            print(f"{k:>20}: {v}")

    print("\nYearly breakdown:")
    print(yearly.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    trades_to_frame(trades).to_csv(RESULTS_DIR / f"trades_{args.label}.csv", index=False)
    yearly.to_csv(RESULTS_DIR / f"yearly_{args.label}.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(equity_curve["time"], equity_curve["equity"], linewidth=1)
    ax.set_title(f"XAUUSD Scalping Strategy Equity Curve ({args.label})")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity (USD)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / f"equity_curve_{args.label}.png", dpi=120)
    print(f"\nSaved trade log, yearly breakdown, and equity curve plot to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
