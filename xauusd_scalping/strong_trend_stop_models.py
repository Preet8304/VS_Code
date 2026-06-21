"""Stop-management + partial-exit simulation, scoped to one regime only:
the 659-trade "Strong Trend" (ADX>=25, ATR-pct>=0.5) bucket that
regime_analysis.py flagged as the largest and weakest of the four regimes
(PF 1.22). Same entries throughout -- nothing about signal generation,
fill price/time, or position sizing (always pinned to the original 0.5x ATR
stop distance) is changed. Only the in-trade stop/partial-exit handling
differs per model.

The bar-by-bar replay must still run across the FULL chronological m15
sequence (position state and "is a position already open" blocking depend
on the whole sequence, not a regime subset) -- only the final REPORTING
step filters the resulting trade list down to the canonical Strong Trend
entry_time set already produced by regime_analysis.py
(`results/trade_regime_full_ecn.csv`). This mirrors the same join approach
session_analysis.py and regime_analysis.py use to slice audit.py's full
trade list.

Five models, all evaluated in R-multiples per the request:
  A: stop -> breakeven after +1R (target untouched)
  B: stop -> +0.5R after +2R (target untouched)
  C: 25% @ +1R, stop -> breakeven on the remaining 75% (target untouched
     on the remainder -- no trailing)
  D: 25% @ +1R, 25% @ +2R, trail the remaining 50% with a Chandelier exit
     (22, 3x ATR -- same plain default as exit_models.py's Model D)
  E: 50% @ +1.5R, trail the remaining 50% with a 3x ATR trail (same plain
     default as exit_models.py/stop_management.py's ATR-trail convention)

For D and E, once trailing begins the fixed 4.5R target is dropped on the
remainder (this is what "trail the remainder" is taken to mean -- the
trailing level becomes the only exit trigger on that size, the same intent
already disclosed in STOP_MANAGEMENT.md). For A/B/C, the original 4.5R
target stays live throughout since none of those three ever start a trail.
A baseline "Current" row (no management at all) is included for direct
comparison -- it is exactly regime_analysis.py's already-published Strong
Trend row, recomputed here only to attach an R-multiple-based max-drawdown
and a max-consecutive-losses count that regime_analysis.py did not compute.

Run `python3 strong_trend_stop_models.py` to reproduce every number in
STRONG_TREND_ANALYSIS.md's stop-management section.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import CostModel, RiskModel, Trade, _initial_stop_tp
from data_loader import load_h1, load_m15
from strategy import StrategyParams, generate_signals

RESULTS_DIR = Path(__file__).resolve().parent / "results"

CHANDELIER_LOOKBACK = 22  # same plain default as exit_models.py Model D
CHANDELIER_MULT = 3.0
ATR_TRAIL_MULT = 3.0      # same plain default used throughout this project

MODELS = ["current", "A", "B", "C", "D", "E"]
MODEL_LABELS = {
    "current": "Current exit, no stop management (baseline)",
    "A": "Model A: stop -> breakeven after +1R",
    "B": "Model B: stop -> +0.5R after +2R",
    "C": "Model C: 25% @ +1R, stop -> breakeven on remainder",
    "D": "Model D: 25% @ +1R, 25% @ +2R, trail remainder (Chandelier 22/3x)",
    "E": "Model E: 50% @ +1.5R, trail remainder (3x ATR)",
}


def simulate(model: str, df: pd.DataFrame, params: StrategyParams, costs: CostModel, risk: RiskModel,
             chand_long: np.ndarray, chand_short: np.ndarray):
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
    rows: list[Trade] = []
    pos = None
    pending = None
    n = len(df)

    for i in range(n):
        if pos is not None:
            direction = pos["direction"]
            bars_held = i - pos["entry_index"]
            time_stop = bars_held >= params.max_holding_bars
            entry_price = pos["entry_price"]
            stop_dist = pos["stop_dist"]

            # Pre-step: ratchet a trailing level using the prior completed
            # bar's data (already lagged in chand_long/chand_short) BEFORE
            # this bar's stop hit-test, exactly mirroring exit_models.py's
            # Model D and stop_management.py's Model F convention.
            if model == "D" and pos["stage"] == "trailing":
                level = chand_long[i] if direction == "long" else chand_short[i]
                if not np.isnan(level):
                    pos["live_stop"] = max(pos["live_stop"], level) if direction == "long" else min(pos["live_stop"], level)
            elif model == "E" and pos["stage"] == "trailing":
                prior_atr = atrs[i - 1] if i > 0 else atrs[i]
                prior_close = closes[i - 1] if i > 0 else closes[i]
                candidate = prior_close - ATR_TRAIL_MULT * prior_atr if direction == "long" else prior_close + ATR_TRAIL_MULT * prior_atr
                pos["live_stop"] = max(pos["live_stop"], candidate) if direction == "long" else min(pos["live_stop"], candidate)

            if direction == "long":
                hit_stop = lows[i] <= pos["live_stop"]
                hit_target = pos["target_active"] and highs[i] >= pos["live_target"]
            else:
                hit_stop = highs[i] >= pos["live_stop"]
                hit_target = pos["target_active"] and lows[i] <= pos["live_target"]

            exit_reason = None
            exit_price = None
            slip = False

            if hit_stop:
                exit_reason, exit_price, slip = pos["stop_label"], pos["live_stop"], True
            elif hit_target:
                exit_reason, exit_price, slip = "take_profit", pos["live_target"], False
            else:
                if model == "A" and pos["stage"] == "initial":
                    trig = entry_price + 1.0 * stop_dist if direction == "long" else entry_price - 1.0 * stop_dist
                    reached = highs[i] >= trig if direction == "long" else lows[i] <= trig
                    if reached:
                        pos["live_stop"], pos["stop_label"], pos["stage"] = entry_price, "breakeven_stop", "breakeven"

                elif model == "B" and pos["stage"] == "initial":
                    trig = entry_price + 2.0 * stop_dist if direction == "long" else entry_price - 2.0 * stop_dist
                    reached = highs[i] >= trig if direction == "long" else lows[i] <= trig
                    if reached:
                        lock = entry_price + 0.5 * stop_dist if direction == "long" else entry_price - 0.5 * stop_dist
                        pos["live_stop"], pos["stop_label"], pos["stage"] = lock, "locked_0.5R_stop", "locked"

                elif model == "C" and pos["stage"] == "initial":
                    trig = entry_price + 1.0 * stop_dist if direction == "long" else entry_price - 1.0 * stop_dist
                    reached = highs[i] >= trig if direction == "long" else lows[i] <= trig
                    if reached:
                        leg_fill = trig - costs.spread / 2 if direction == "long" else trig + costs.spread / 2
                        leg_pnl = ((leg_fill - entry_price) if direction == "long" else (entry_price - leg_fill)) * pos["size_oz"] * 0.25
                        pos["realized_pnl"] += leg_pnl
                        equity += leg_pnl
                        pos["live_stop"], pos["stop_label"] = entry_price, "breakeven_stop"
                        pos["stage"], pos["remaining_frac"] = "partial_done", 0.75

                elif model == "D":
                    if pos["stage"] == "initial":
                        trig = entry_price + 1.0 * stop_dist if direction == "long" else entry_price - 1.0 * stop_dist
                        reached = highs[i] >= trig if direction == "long" else lows[i] <= trig
                        if reached:
                            leg_fill = trig - costs.spread / 2 if direction == "long" else trig + costs.spread / 2
                            leg_pnl = ((leg_fill - entry_price) if direction == "long" else (entry_price - leg_fill)) * pos["size_oz"] * 0.25
                            pos["realized_pnl"] += leg_pnl
                            equity += leg_pnl
                            pos["remaining_frac"], pos["stage"] = 0.75, "partial1_done"
                    elif pos["stage"] == "partial1_done":
                        trig = entry_price + 2.0 * stop_dist if direction == "long" else entry_price - 2.0 * stop_dist
                        reached = highs[i] >= trig if direction == "long" else lows[i] <= trig
                        if reached:
                            leg_fill = trig - costs.spread / 2 if direction == "long" else trig + costs.spread / 2
                            leg_pnl = ((leg_fill - entry_price) if direction == "long" else (entry_price - leg_fill)) * pos["size_oz"] * 0.25
                            pos["realized_pnl"] += leg_pnl
                            equity += leg_pnl
                            pos["remaining_frac"], pos["stage"] = 0.5, "trailing"
                            pos["target_active"] = False
                            level = chand_long[i] if direction == "long" else chand_short[i]
                            base = entry_price
                            if not np.isnan(level):
                                base = max(entry_price, level) if direction == "long" else min(entry_price, level)
                            pos["live_stop"], pos["stop_label"] = base, "chandelier_stop"

                elif model == "E" and pos["stage"] == "initial":
                    trig = entry_price + 1.5 * stop_dist if direction == "long" else entry_price - 1.5 * stop_dist
                    reached = highs[i] >= trig if direction == "long" else lows[i] <= trig
                    if reached:
                        leg_fill = trig - costs.spread / 2 if direction == "long" else trig + costs.spread / 2
                        leg_pnl = ((leg_fill - entry_price) if direction == "long" else (entry_price - leg_fill)) * pos["size_oz"] * 0.5
                        pos["realized_pnl"] += leg_pnl
                        equity += leg_pnl
                        pos["remaining_frac"], pos["stage"] = 0.5, "trailing"
                        pos["target_active"] = False
                        pos["live_stop"], pos["stop_label"] = entry_price, "atr_trail_stop"

                if time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            if exit_reason is not None:
                closed_frac = pos["remaining_frac"]
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                if slip:
                    fill = fill - costs.stop_slippage if direction == "long" else fill + costs.stop_slippage
                leg_pnl = ((fill - entry_price) if direction == "long" else (entry_price - fill)) * pos["size_oz"] * closed_frac
                pos["realized_pnl"] += leg_pnl
                equity += leg_pnl
                r_multiple = pos["realized_pnl"] / pos["risk_dollars"] if pos["risk_dollars"] else 0.0
                rows.append(
                    Trade(
                        entry_time=pos["entry_time"], exit_time=times[i], direction=direction,
                        entry_price=entry_price, exit_price=fill, stop_price=pos["orig_stop"],
                        take_profit=pos["orig_target"], size_oz=pos["size_oz"], pnl=pos["realized_pnl"],
                        r_multiple=r_multiple, exit_reason=exit_reason, bars_held=bars_held,
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
                "direction": direction, "entry_time": times[i], "entry_index": i, "entry_price": entry_price,
                "orig_stop": orig_stop, "orig_target": orig_target, "live_stop": orig_stop, "stop_label": "stop_loss",
                "live_target": orig_target, "target_active": True, "stop_dist": stop_dist,
                "risk_dollars": risk_dollars, "size_oz": size_oz, "realized_pnl": 0.0,
                "stage": "initial", "remaining_frac": 1.0,
            }
            pending = None

        if pos is None and pending is None:
            if long_sig[i]:
                pending = "long"
            elif short_sig[i]:
                pending = "short"

    return rows


def trades_to_df(rows: list[Trade]) -> pd.DataFrame:
    return pd.DataFrame([t.__dict__ for t in rows])


def filter_to_strong_trend(tdf: pd.DataFrame, strong_trend_entry_times: pd.Series) -> pd.DataFrame:
    mask = tdf["entry_time"].isin(set(strong_trend_entry_times))
    return tdf[mask].sort_values("entry_time").reset_index(drop=True)


def equity_curve_from_r(r_multiples: pd.Series, initial_equity: float, risk_per_trade: float) -> pd.Series:
    return initial_equity * (1.0 + r_multiples * risk_per_trade).cumprod()


def max_drawdown_pct(r_multiples: pd.Series, initial_equity: float, risk_per_trade: float) -> float:
    equity = equity_curve_from_r(r_multiples, initial_equity, risk_per_trade)
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    return float(dd.min()) if len(dd) else 0.0


def max_consecutive_losses(r_multiples: pd.Series) -> int:
    worst = cur = 0
    for r in r_multiples:
        if r <= 0:
            cur += 1
            worst = max(worst, cur)
        else:
            cur = 0
    return worst


def r_stats(tdf: pd.DataFrame, risk: RiskModel) -> dict:
    n = len(tdf)
    r = tdf["r_multiple"]
    wins = r[r > 0]
    losses = r[r <= 0]
    gp = wins.sum()
    gl = -losses.sum()
    return {
        "trades": n,
        "win_rate": len(wins) / n if n else 0.0,
        "profit_factor": gp / gl if gl > 0 else float("inf"),
        "expectancy_r": r.mean() if n else 0.0,
        "avg_r": r.mean() if n else 0.0,
        "max_drawdown_pct": max_drawdown_pct(r, risk.initial_equity, risk.risk_per_trade) * 100,
        "max_consec_losses": max_consecutive_losses(r),
    }


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()
    costs = CostModel(spread=0.10, stop_slippage=0.03)
    risk = RiskModel()

    df = generate_signals(m15, h1, params)
    hh = df["high"].rolling(CHANDELIER_LOOKBACK).max()
    ll = df["low"].rolling(CHANDELIER_LOOKBACK).min()
    chand_long = (hh - CHANDELIER_MULT * df["atr"]).shift(1).to_numpy()
    chand_short = (ll + CHANDELIER_MULT * df["atr"]).shift(1).to_numpy()

    regime_csv = pd.read_csv(RESULTS_DIR / "trade_regime_full_ecn.csv", parse_dates=["entry_time"])
    strong_trend_entries = regime_csv.loc[regime_csv["regime"] == "Strong Trend", "entry_time"]
    print(f"canonical Strong Trend entries: n={len(strong_trend_entries)}")

    RESULTS_DIR.mkdir(exist_ok=True)
    summary_rows = []
    for model in MODELS:
        rows = simulate(model, df, params, costs, risk, chand_long, chand_short)
        tdf_full = trades_to_df(rows)
        tdf = filter_to_strong_trend(tdf_full, strong_trend_entries)
        stats = r_stats(tdf, risk)
        stats["model"] = model
        stats["label"] = MODEL_LABELS[model]
        summary_rows.append(stats)
        print(
            f"{model:8s} n={stats['trades']:4d} wr={stats['win_rate']:.4f} "
            f"pf={stats['profit_factor']:.4f} exp_r={stats['expectancy_r']:.4f} "
            f"mdd={stats['max_drawdown_pct']:.2f}% max_consec_loss={stats['max_consec_losses']}"
        )

    out = pd.DataFrame(summary_rows)
    out.to_csv(RESULTS_DIR / "strong_trend_stop_models_summary.csv", index=False)
    print(f"saved -> {RESULTS_DIR / 'strong_trend_stop_models_summary.csv'}")


if __name__ == "__main__":
    main()
