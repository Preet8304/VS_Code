"""Stop-management overlay comparison: identical entries AND identical target
(the locked 4.5x ATR take-profit) AND identical 12-bar time stop -- only the
STOP placement during the trade differs per model. This is a narrower
question than exit_models.py: "how much is left on the table by never moving
the stop off its initial 0.5x ATR placement," not "what if the whole exit
were replaced."

Conservative, existing-engine convention preserved throughout: within a bar,
the stop level in force *before* that bar is checked first (a stop-adjust
trigger and a stop hit are never allowed to resolve in the trade's favor
within the same bar -- the worse case wins ties), exactly mirroring
backtest.py's documented SL-first assumption.

Position sizing is pinned to the original 0.5x ATR stop distance for every
model (same as exit_models.py), so R always means the same dollar amount.

Run `python3 stop_management.py` to reproduce every number in
STOP_MANAGEMENT.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import CostModel, RiskModel, Trade, _initial_stop_tp
from data_loader import load_h1, load_m15
from metrics import summarize
from strategy import StrategyParams, generate_signals

RESULTS_DIR = Path(__file__).resolve().parent / "results"

ATR_TRAIL_MULT = 3.0  # same plain "3x ATR" convention used in exit_models.py Model B

MODELS = ["A", "B", "C", "D", "E", "F"]
MODEL_LABELS = {
    "A": "Model A: current exit (no stop management)",
    "B": "Model B: stop -> breakeven after +1R",
    "C": "Model C: stop -> breakeven after +1.5R",
    "D": "Model D: stop -> +0.5R after +2R",
    "E": "Model E: 50% @ +1.5R, stop -> breakeven on remainder",
    "F": "Model F: 25% @ +1R, 25% @ +2R, trail remainder 3x ATR",
}


def simulate(model: str, df: pd.DataFrame, params: StrategyParams, costs: CostModel, risk: RiskModel):
    times = df["time"].to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    atrs = df["atr"].to_numpy()
    smas = df["sma"].to_numpy()
    long_sig = df["long_signal"].to_numpy()
    short_sig = df["short_signal"].to_numpy()

    equity = risk.initial_equity
    equity_curve = np.empty(len(df))
    rows: list[Trade] = []
    pos = None
    pending = None
    n = len(df)

    for i in range(n):
        equity_curve[i] = equity

        if pos is not None:
            direction = pos["direction"]
            bars_held = i - pos["entry_index"]
            time_stop = bars_held >= params.max_holding_bars
            stop_dist = pos["stop_dist"]
            entry_price = pos["entry_price"]

            if direction == "long":
                hit_stop = lows[i] <= pos["live_stop"]
                hit_target = highs[i] >= pos["live_target"]
            else:
                hit_stop = highs[i] >= pos["live_stop"]
                hit_target = lows[i] <= pos["live_target"]

            exit_reason = None
            exit_price = None
            slip = False

            if hit_stop:
                exit_reason, exit_price, slip = pos["stop_label"], pos["live_stop"], True
            elif hit_target:
                exit_reason, exit_price, slip = "take_profit", pos["live_target"], False
            else:
                # Stop/target untouched this bar: check management triggers
                # (these adjust state for FUTURE bars, they never exit a trade
                # themselves) before falling through to the time-stop backstop.
                if model == "B" and pos["stage"] == "initial":
                    trigger_price = entry_price + 1.0 * stop_dist if direction == "long" else entry_price - 1.0 * stop_dist
                    reached = highs[i] >= trigger_price if direction == "long" else lows[i] <= trigger_price
                    if reached:
                        pos["live_stop"] = entry_price
                        pos["stop_label"] = "breakeven_stop"
                        pos["stage"] = "breakeven"

                elif model == "C" and pos["stage"] == "initial":
                    trigger_price = entry_price + 1.5 * stop_dist if direction == "long" else entry_price - 1.5 * stop_dist
                    reached = highs[i] >= trigger_price if direction == "long" else lows[i] <= trigger_price
                    if reached:
                        pos["live_stop"] = entry_price
                        pos["stop_label"] = "breakeven_stop"
                        pos["stage"] = "breakeven"

                elif model == "D" and pos["stage"] == "initial":
                    trigger_price = entry_price + 2.0 * stop_dist if direction == "long" else entry_price - 2.0 * stop_dist
                    reached = highs[i] >= trigger_price if direction == "long" else lows[i] <= trigger_price
                    if reached:
                        lock_price = entry_price + 0.5 * stop_dist if direction == "long" else entry_price - 0.5 * stop_dist
                        pos["live_stop"] = lock_price
                        pos["stop_label"] = "locked_0.5R_stop"
                        pos["stage"] = "locked"

                elif model == "E" and pos["stage"] == "initial":
                    trigger_price = entry_price + 1.5 * stop_dist if direction == "long" else entry_price - 1.5 * stop_dist
                    reached = highs[i] >= trigger_price if direction == "long" else lows[i] <= trigger_price
                    if reached:
                        leg_fill = trigger_price - costs.spread / 2 if direction == "long" else trigger_price + costs.spread / 2
                        leg_pnl = (
                            (leg_fill - entry_price) * pos["size_oz"] * 0.5
                            if direction == "long"
                            else (entry_price - leg_fill) * pos["size_oz"] * 0.5
                        )
                        pos["realized_pnl"] += leg_pnl
                        equity += leg_pnl
                        pos["live_stop"] = entry_price
                        pos["stop_label"] = "breakeven_stop"
                        pos["stage"] = "partial_done"
                        pos["remaining_frac"] = 0.5

                elif model == "F":
                    if pos["stage"] == "initial":
                        trigger_price = entry_price + 1.0 * stop_dist if direction == "long" else entry_price - 1.0 * stop_dist
                        reached = highs[i] >= trigger_price if direction == "long" else lows[i] <= trigger_price
                        if reached:
                            leg_fill = trigger_price - costs.spread / 2 if direction == "long" else trigger_price + costs.spread / 2
                            leg_pnl = (
                                (leg_fill - entry_price) * pos["size_oz"] * 0.25
                                if direction == "long"
                                else (entry_price - leg_fill) * pos["size_oz"] * 0.25
                            )
                            pos["realized_pnl"] += leg_pnl
                            equity += leg_pnl
                            pos["remaining_frac"] = 0.75
                            pos["stage"] = "partial1_done"
                    elif pos["stage"] == "partial1_done":
                        trigger_price = entry_price + 2.0 * stop_dist if direction == "long" else entry_price - 2.0 * stop_dist
                        reached = highs[i] >= trigger_price if direction == "long" else lows[i] <= trigger_price
                        if reached:
                            leg_fill = trigger_price - costs.spread / 2 if direction == "long" else trigger_price + costs.spread / 2
                            leg_pnl = (
                                (leg_fill - entry_price) * pos["size_oz"] * 0.25
                                if direction == "long"
                                else (entry_price - leg_fill) * pos["size_oz"] * 0.25
                            )
                            pos["realized_pnl"] += leg_pnl
                            equity += leg_pnl
                            pos["remaining_frac"] = 0.5
                            pos["stage"] = "trailing"
                            # Trailing replaces the fixed target on the remainder; lock
                            # in at least breakeven before the ATR trail takes over.
                            pos["live_stop"] = entry_price
                            pos["stop_label"] = "atr_trail_stop"
                    elif pos["stage"] == "trailing":
                        prior_atr = atrs[i - 1] if i > 0 else atrs[i]
                        prior_close = closes[i - 1] if i > 0 else closes[i]
                        if direction == "long":
                            candidate = prior_close - ATR_TRAIL_MULT * prior_atr
                            pos["live_stop"] = max(pos["live_stop"], candidate)
                        else:
                            candidate = prior_close + ATR_TRAIL_MULT * prior_atr
                            pos["live_stop"] = min(pos["live_stop"], candidate)

                if time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            if exit_reason is not None:
                closed_frac = pos["remaining_frac"]
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                if slip:
                    fill = fill - costs.stop_slippage if direction == "long" else fill + costs.stop_slippage
                leg_pnl = (
                    (fill - entry_price) * pos["size_oz"] * closed_frac
                    if direction == "long"
                    else (entry_price - fill) * pos["size_oz"] * closed_frac
                )
                pos["realized_pnl"] += leg_pnl
                equity += leg_pnl
                equity_curve[i] = equity
                r_multiple = pos["realized_pnl"] / pos["risk_dollars"] if pos["risk_dollars"] else 0.0
                rows.append(
                    Trade(
                        entry_time=pos["entry_time"],
                        exit_time=times[i],
                        direction=direction,
                        entry_price=entry_price,
                        exit_price=fill,
                        stop_price=pos["orig_stop"],
                        take_profit=pos["live_target"],
                        size_oz=pos["size_oz"],
                        pnl=pos["realized_pnl"],
                        r_multiple=r_multiple,
                        exit_reason=exit_reason,
                        bars_held=bars_held,
                    )
                )
                pos = None

        if pending is not None and pos is None:
            direction = pending
            entry_price = opens[i] + costs.spread / 2 if direction == "long" else opens[i] - costs.spread / 2
            sig_idx = i - 1 if i > 0 else i
            atr_value = atrs[sig_idx]
            sma_value = smas[sig_idx]
            orig_stop, orig_target = _initial_stop_tp(direction, entry_price, atr_value, sma_value, params)
            stop_dist = abs(entry_price - orig_stop)
            risk_dollars = equity * risk.risk_per_trade
            size_oz = risk_dollars / stop_dist if stop_dist > 0 else 0.0

            pos = {
                "direction": direction,
                "entry_time": times[i],
                "entry_index": i,
                "entry_price": entry_price,
                "orig_stop": orig_stop,
                "live_stop": orig_stop,
                "stop_label": "stop_loss",
                "live_target": orig_target,
                "stop_dist": stop_dist,
                "risk_dollars": risk_dollars,
                "size_oz": size_oz,
                "realized_pnl": 0.0,
                "stage": "initial",
                "remaining_frac": 1.0,
            }
            pending = None

        if pos is None and pending is None:
            if long_sig[i]:
                pending = "long"
            elif short_sig[i]:
                pending = "short"

    equity_curve_df = df[["time"]].copy()
    equity_curve_df["equity"] = equity_curve
    return rows, equity_curve_df


def max_consecutive_losses(trades: list[Trade]) -> int:
    worst = cur = 0
    for t in trades:
        if t.pnl <= 0:
            cur += 1
            worst = max(worst, cur)
        else:
            cur = 0
    return worst


def annual_return_pct(trades: list[Trade], initial_equity: float) -> float:
    if not trades:
        return 0.0
    tdf = pd.DataFrame([t.__dict__ for t in trades])
    years = (tdf["exit_time"].iloc[-1] - tdf["entry_time"].iloc[0]).days / 365.25
    final_equity = initial_equity + tdf["pnl"].sum()
    if years <= 0:
        return 0.0
    return (((final_equity / initial_equity) ** (1 / years)) - 1) * 100


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()
    costs = CostModel(spread=0.10, stop_slippage=0.03)
    risk = RiskModel()

    df = generate_signals(m15, h1, params)

    RESULTS_DIR.mkdir(exist_ok=True)
    summary_rows = []
    for model in MODELS:
        trades, eq_curve = simulate(model, df, params, costs, risk)
        stats = summarize(trades, eq_curve, risk.initial_equity)
        stats["model"] = model
        stats["label"] = MODEL_LABELS[model]
        stats["max_consec_losses"] = max_consecutive_losses(trades)
        stats["annual_return_pct"] = annual_return_pct(trades, risk.initial_equity)
        summary_rows.append(stats)
        print(
            f"{model:3s} n={stats['total_trades']:5d} wr={stats['win_rate']:.4f} "
            f"pf={stats['profit_factor']:.4f} exp_r={stats['expectancy_r']:.4f} "
            f"avg_win=${stats['avg_win_usd']:.2f} avg_loss=${stats['avg_loss_usd']:.2f} "
            f"mdd={stats['max_drawdown_pct']:.2f}% sharpe={stats['sharpe']:.3f} "
            f"max_consec_loss={stats['max_consec_losses']} ann_ret={stats['annual_return_pct']:.2f}%"
        )

    out = pd.DataFrame(summary_rows)
    out.to_csv(RESULTS_DIR / "stop_management_summary.csv", index=False)
    print(f"saved -> {RESULTS_DIR / 'stop_management_summary.csv'}")


if __name__ == "__main__":
    main()
