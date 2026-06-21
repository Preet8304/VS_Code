"""Session breakdown of the locked strategy's existing trades.

Read-only research tool. Reuses audit.run_audit() verbatim for the trade
list (nothing about entries/exits is touched) and classifies each trade by
entry hour (platform time, see data_loader.py) into the four standard,
textbook forex session windows -- not tuned, not searched:

    Asian              00:00-08:00
    London             08:00-13:00  (pre-overlap)
    London/NY overlap  13:00-17:00
    New York           17:00-22:00  (post-overlap)

These are the conventional session boundaries (Investopedia/most broker
session-clock conventions), applied directly to the dataset's recorded hour
values with the same platform-time caveat data_loader.py already documents
(the feed is not strictly UTC, so these are approximate, disclosed
boundaries, not a fitted split).

Because the strategy's own session filter is locked to platform hours
13:00-16:00 -- entirely inside the 13:00-17:00 overlap window above -- every
single trade is expected to land in one bucket. That is reported as the
finding, not treated as a bug (see RESULTS.md / EDGE_ANALYSIS.md S9-S10 for
why this window was chosen, and audit.py's similar "session-bucket
triviality" note from the trade-by-trade audit).

Run `python3 session_analysis.py` to reproduce every number in
SESSION_ANALYSIS.md.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from audit import run_audit
from backtest import CostModel, RiskModel
from data_loader import load_h1, load_m15
from strategy import StrategyParams

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def classify_session(hour: int) -> str:
    if 0 <= hour < 8:
        return "Asian"
    if 8 <= hour < 13:
        return "London"
    if 13 <= hour < 17:
        return "London+NY overlap"
    if 17 <= hour < 22:
        return "New York"
    return "Other"


def trade_level_max_drawdown(r_multiples: pd.Series, initial_equity: float, risk_per_trade: float) -> float:
    """Reconstructs a fresh compounding equity curve from this subgroup's own
    R-multiples (equity *= 1 + r*risk_per_trade per trade -- the same relation
    the real backtest uses internally), rather than reusing the dollar pnl
    figures from the full run. Those dollar figures were sized off the real,
    much-larger compounded equity at that point in history, so summing them
    against a fresh $initial_equity baseline (as a naive pnl.cumsum() would)
    produces a meaningless, sometimes >100%, drawdown for any subgroup that
    isn't the entire chronological trade sequence from the very first trade.
    """
    equity = initial_equity * (1.0 + r_multiples * risk_per_trade).cumprod()
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min()) if len(drawdown) else 0.0


def summarize_group(group: pd.DataFrame, initial_equity: float, risk_per_trade: float) -> dict:
    n = len(group)
    wins = group[group["pnl"] > 0]
    losses = group[group["pnl"] <= 0]
    gp = wins["pnl"].sum()
    gl = -losses["pnl"].sum()
    return {
        "trades": n,
        "win_rate": len(wins) / n if n else 0.0,
        "profit_factor": gp / gl if gl > 0 else float("inf"),
        "avg_r": group["r_multiple"].mean() if n else 0.0,
        "max_drawdown_pct": trade_level_max_drawdown(group["r_multiple"], initial_equity, risk_per_trade) * 100 if n else 0.0,
    }


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()
    costs = CostModel(spread=0.10, stop_slippage=0.03)
    risk = RiskModel()

    trades = run_audit(m15, h1, params, costs, risk)
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["session"] = trades["entry_time"].dt.hour.apply(classify_session)
    trades["year"] = trades["entry_time"].dt.year

    RESULTS_DIR.mkdir(exist_ok=True)
    trades.to_csv(RESULTS_DIR / "trade_session_full_ecn.csv", index=False)

    sessions = ["Asian", "London", "London+NY overlap", "New York", "Other"]
    rows = []
    for session in sessions:
        g = trades[trades["session"] == session]
        stats = summarize_group(g, risk.initial_equity, risk.risk_per_trade)
        stats["session"] = session
        rows.append(stats)
    overall = pd.DataFrame(rows)
    overall.to_csv(RESULTS_DIR / "session_summary.csv", index=False)

    print(f"n_trades={len(trades)}")
    for r in rows:
        print(
            f"{r['session']:20s} n={r['trades']:5d} wr={r['win_rate']:.4f} "
            f"pf={r['profit_factor']:.4f} avg_r={r['avg_r']:.4f} "
            f"mdd={r['max_drawdown_pct']:.2f}%"
        )

    by_year_rows = []
    for (session, year), g in trades.groupby(["session", "year"]):
        if len(g) == 0:
            continue
        stats = summarize_group(g, risk.initial_equity, risk.risk_per_trade)
        stats["session"] = session
        stats["year"] = int(year)
        by_year_rows.append(stats)
    by_year = pd.DataFrame(by_year_rows)
    by_year.to_csv(RESULTS_DIR / "session_by_year.csv", index=False)

    dominant = overall.loc[overall["trades"].idxmax(), "session"]
    dominant_share = overall.loc[overall["trades"].idxmax(), "trades"] / len(trades)
    print(f"dominant session: {dominant} ({dominant_share:.1%} of all trades)")
    print(f"saved -> {RESULTS_DIR / 'session_summary.csv'}, {RESULTS_DIR / 'session_by_year.csv'}")


if __name__ == "__main__":
    main()
