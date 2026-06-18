"""Performance metrics for a list of closed trades + equity curve."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import Trade


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(
            columns=[
                "entry_time", "exit_time", "direction", "entry_price", "exit_price",
                "stop_price", "take_profit", "size_oz", "pnl", "r_multiple",
                "exit_reason", "bars_held",
            ]
        )
    return pd.DataFrame([t.__dict__ for t in trades])


def max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min())


def annualized_sharpe(equity_curve: pd.DataFrame, initial_equity: float) -> float:
    daily = equity_curve.set_index("time")["equity"].resample("1D").last().ffill()
    daily_returns = daily.pct_change().dropna()
    if daily_returns.std() == 0 or len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))


def summarize(trades: list[Trade], equity_curve: pd.DataFrame, initial_equity: float) -> dict:
    tdf = trades_to_frame(trades)
    n = len(tdf)
    if n == 0:
        return {"total_trades": 0}

    wins = tdf[tdf["pnl"] > 0]
    losses = tdf[tdf["pnl"] <= 0]
    gross_profit = wins["pnl"].sum()
    gross_loss = -losses["pnl"].sum()
    final_equity = initial_equity + tdf["pnl"].sum()

    years = (equity_curve["time"].iloc[-1] - equity_curve["time"].iloc[0]).days / 365.25
    cagr = (final_equity / initial_equity) ** (1 / years) - 1 if years > 0 else float("nan")

    return {
        "total_trades": n,
        "win_rate": len(wins) / n,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "avg_win_usd": wins["pnl"].mean() if len(wins) else 0.0,
        "avg_loss_usd": losses["pnl"].mean() if len(losses) else 0.0,
        "avg_r": tdf["r_multiple"].mean(),
        "expectancy_usd": tdf["pnl"].mean(),
        "expectancy_r": tdf["r_multiple"].mean(),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "initial_equity": initial_equity,
        "final_equity": final_equity,
        "total_return_pct": (final_equity / initial_equity - 1) * 100,
        "cagr_pct": cagr * 100,
        "max_drawdown_pct": max_drawdown(equity_curve["equity"]) * 100,
        "sharpe": annualized_sharpe(equity_curve, initial_equity),
        "avg_bars_held": tdf["bars_held"].mean(),
        "long_trades": int((tdf["direction"] == "long").sum()),
        "short_trades": int((tdf["direction"] == "short").sum()),
        "stop_loss_exits": int((tdf["exit_reason"] == "stop_loss").sum()),
        "take_profit_exits": int((tdf["exit_reason"] == "take_profit").sum()),
        "time_stop_exits": int((tdf["exit_reason"] == "time_stop").sum()),
    }


def yearly_breakdown(trades: list[Trade], initial_equity: float) -> pd.DataFrame:
    tdf = trades_to_frame(trades)
    if tdf.empty:
        return pd.DataFrame()
    tdf["year"] = pd.to_datetime(tdf["exit_time"]).dt.year
    rows = []
    running_equity = initial_equity
    for year, group in tdf.groupby("year"):
        n = len(group)
        wins = group[group["pnl"] > 0]
        pnl = group["pnl"].sum()
        start_equity = running_equity
        running_equity += pnl
        rows.append(
            {
                "year": int(year),
                "trades": n,
                "win_rate_pct": len(wins) / n * 100,
                "pnl_usd": pnl,
                "return_pct": pnl / start_equity * 100,
                "end_equity": running_equity,
            }
        )
    return pd.DataFrame(rows)
