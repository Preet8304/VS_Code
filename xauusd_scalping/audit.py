"""Trade-by-trade diagnostic audit of the locked XAUUSD strategy.

Read-only research tool. It runs the existing strategy/backtest exactly as
defined in strategy.py/backtest.py -- no parameters are changed -- and
attaches diagnostic columns per trade (MFE/MAE in R, session bucket, ATR
percentile and trend state at entry, and liquidity-sweep flags) that the
production Trade record does not carry. The bar-by-bar fill/exit logic below
is a line-for-line mirror of backtest.run_backtest(); it exists separately
only so MFE/MAE and entry-context can be captured without touching the
production engine. Run `python3 audit.py` to reproduce every number in
AUDIT.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import CostModel, RiskModel, _initial_stop_tp
from data_loader import load_h1, load_m15
from strategy import StrategyParams, generate_signals

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _session_bucket(hour: int) -> str:
    # Platform time (UTC+2/3-ish, see data_loader.py). Buckets are the usual
    # forex convention shifted into platform time; the strategy's own session
    # filter (13:00-16:00) sits inside "ny" by this convention.
    if 0 <= hour < 7:
        return "asian"
    if 7 <= hour < 13:
        return "london"
    if 13 <= hour < 21:
        return "ny"
    return "late_ny"


def _sweep_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = out["time"].dt.date
    daily = out.groupby("date").agg(day_low=("low", "min"), day_high=("high", "max")).reset_index()
    daily["prev_day_low"] = daily["day_low"].shift(1)
    daily["prev_day_high"] = daily["day_high"].shift(1)
    out = out.merge(daily[["date", "prev_day_low", "prev_day_high"]], on="date", how="left")

    out["week"] = out["time"].dt.to_period("W")
    weekly = out.groupby("week").agg(week_low=("low", "min"), week_high=("high", "max")).reset_index()
    weekly["prev_week_low"] = weekly["week_low"].shift(1)
    weekly["prev_week_high"] = weekly["week_high"].shift(1)
    out = out.merge(weekly[["week", "prev_week_low", "prev_week_high"]], on="week", how="left")

    out["low_sweeps_day"] = out["low"] < out["prev_day_low"]
    out["high_sweeps_day"] = out["high"] > out["prev_day_high"]
    out["low_sweeps_week"] = out["low"] < out["prev_week_low"]
    out["high_sweeps_week"] = out["high"] > out["prev_week_high"]
    return out


def run_audit(
    m15: pd.DataFrame, h1: pd.DataFrame, params: StrategyParams, costs: CostModel, risk: RiskModel
) -> pd.DataFrame:
    df = generate_signals(m15, h1, params)
    df = _sweep_flags(df)

    times = df["time"].to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    atrs = df["atr"].to_numpy()
    smas = df["sma"].to_numpy()
    atr_pcts = df["atr_pct"].to_numpy()
    trend_up = df["htf_trend_up"].to_numpy()
    trend_down = df["htf_trend_down"].to_numpy()
    long_sig = df["long_signal"].to_numpy()
    short_sig = df["short_signal"].to_numpy()
    low_sweeps_day = df["low_sweeps_day"].to_numpy()
    high_sweeps_day = df["high_sweeps_day"].to_numpy()
    low_sweeps_week = df["low_sweeps_week"].to_numpy()
    high_sweeps_week = df["high_sweeps_week"].to_numpy()

    equity = risk.initial_equity
    rows = []
    pos = None
    pending = None
    n = len(df)

    for i in range(n):
        if pos is not None:
            direction = pos["direction"]
            mfe_before_this_bar = pos["mfe"]  # excludes this (possibly final) bar -- sequence-safe
            if direction == "long":
                hit_sl = lows[i] <= pos["stop_price"]
                hit_tp = pos["take_profit"] is not None and highs[i] >= pos["take_profit"]
                closed_green = closes[i] > pos["entry_price"]
                pos["mfe"] = max(pos["mfe"], highs[i] - pos["entry_price"])
                pos["mae"] = max(pos["mae"], pos["entry_price"] - lows[i])
            else:
                hit_sl = highs[i] >= pos["stop_price"]
                hit_tp = pos["take_profit"] is not None and lows[i] <= pos["take_profit"]
                closed_green = closes[i] < pos["entry_price"]
                pos["mfe"] = max(pos["mfe"], pos["entry_price"] - lows[i])
                pos["mae"] = max(pos["mae"], highs[i] - pos["entry_price"])

            bars_held = i - pos["entry_index"]
            time_stop = bars_held >= params.max_holding_bars

            exit_reason = None
            exit_price = None
            if hit_sl:
                exit_reason = "stop_loss"
                raw_exit = pos["stop_price"]
                exit_price = raw_exit - costs.stop_slippage if direction == "long" else raw_exit + costs.stop_slippage
            elif hit_tp:
                exit_reason = "take_profit"
                exit_price = pos["take_profit"]
            elif params.exit_mode == "first_green" and closed_green:
                exit_reason = "first_green"
                exit_price = closes[i]
            elif time_stop:
                exit_reason = "time_stop"
                raw_exit = closes[i]
                exit_price = raw_exit - costs.stop_slippage if direction == "long" else raw_exit + costs.stop_slippage

            if exit_reason is not None:
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                pnl = (
                    (fill - pos["entry_price"]) * pos["size_oz"]
                    if direction == "long"
                    else (pos["entry_price"] - fill) * pos["size_oz"]
                )
                equity += pnl
                r_multiple = pnl / pos["risk_dollars"] if pos["risk_dollars"] else 0.0
                stop_dist = pos["stop_dist"]

                if pos["day_sweep"] and pos["week_sweep"]:
                    sweep_bucket = "both"
                elif pos["day_sweep"]:
                    sweep_bucket = "prev_day_sweep"
                elif pos["week_sweep"]:
                    sweep_bucket = "prev_week_sweep"
                else:
                    sweep_bucket = "no_sweep"

                rows.append(
                    {
                        "entry_time": pos["entry_time"],
                        "exit_time": times[i],
                        "direction": direction,
                        "entry_price": pos["entry_price"],
                        "stop_price": pos["stop_price"],
                        "take_profit": pos["take_profit"],
                        "exit_price": fill,
                        "pnl": pnl,
                        "equity_after": equity,
                        "r_multiple": r_multiple,
                        "mfe_r": pos["mfe"] / stop_dist if stop_dist else 0.0,
                        "mae_r": pos["mae"] / stop_dist if stop_dist else 0.0,
                        # MFE using only bars strictly before the exit bar -- sequence-known,
                        # unlike mfe_r above which can include same-bar-as-exit ambiguity.
                        "mfe_r_prior_bars": mfe_before_this_bar / stop_dist if stop_dist else 0.0,
                        "exit_reason": exit_reason,
                        "bars_held": bars_held,
                        "holding_minutes": bars_held * 15,
                        "atr_pct_entry": pos["atr_pct_entry"],
                        "trend_state": pos["trend_state"],
                        "session": _session_bucket(pd.Timestamp(pos["entry_time"]).hour),
                        "day_sweep": bool(pos["day_sweep"]),
                        "week_sweep": bool(pos["week_sweep"]),
                        "sweep_bucket": sweep_bucket,
                    }
                )
                pos = None

        if pending is not None and pos is None:
            direction = pending
            entry_price = opens[i] + costs.spread / 2 if direction == "long" else opens[i] - costs.spread / 2
            sig_idx = i - 1 if i > 0 else i
            atr_value = atrs[sig_idx]
            sma_value = smas[sig_idx]
            stop_price, take_profit = _initial_stop_tp(direction, entry_price, atr_value, sma_value, params)
            stop_dist = abs(entry_price - stop_price)
            risk_dollars = equity * risk.risk_per_trade
            size_oz = risk_dollars / stop_dist if stop_dist > 0 else 0.0

            if direction == "long":
                day_sweep = bool(low_sweeps_day[sig_idx])
                week_sweep = bool(low_sweeps_week[sig_idx])
            else:
                day_sweep = bool(high_sweeps_day[sig_idx])
                week_sweep = bool(high_sweeps_week[sig_idx])

            pos = {
                "direction": direction,
                "entry_time": times[i],
                "entry_index": i,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profit": take_profit,
                "size_oz": size_oz,
                "risk_dollars": risk_dollars,
                "stop_dist": stop_dist,
                "mfe": 0.0,
                "mae": 0.0,
                "atr_pct_entry": atr_pcts[sig_idx],
                "trend_state": "up" if trend_up[sig_idx] else ("down" if trend_down[sig_idx] else "none"),
                "day_sweep": day_sweep,
                "week_sweep": week_sweep,
            }
            pending = None

        if pos is None and pending is None:
            if long_sig[i]:
                pending = "long"
            elif short_sig[i]:
                pending = "short"

    return pd.DataFrame(rows)


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()  # locked production defaults, unchanged
    costs = CostModel(spread=0.10, stop_slippage=0.03)  # tight-ECN, the documented viable scenario
    risk = RiskModel()

    trades = run_audit(m15, h1, params, costs, risk)
    RESULTS_DIR.mkdir(exist_ok=True)
    trades.to_csv(RESULTS_DIR / "trade_audit_full_ecn.csv", index=False)
    print(f"n_trades={len(trades)}")
    print(f"win_rate={(trades['pnl'] > 0).mean():.4f}")
    gp = trades.loc[trades['pnl'] > 0, 'pnl'].sum()
    gl = -trades.loc[trades['pnl'] <= 0, 'pnl'].sum()
    print(f"profit_factor={gp / gl:.4f}")
    print(f"saved -> {RESULTS_DIR / 'trade_audit_full_ecn.csv'}")


if __name__ == "__main__":
    main()
