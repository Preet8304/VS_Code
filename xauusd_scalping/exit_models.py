"""Exit-model comparison: identical entries, six different in-trade exit rules.

Read-only research tool. Entries (signal bar, direction, fill price/time, and
position size) are taken from the exact same `generate_signals()` output the
production engine uses -- nothing about entries is changed or tuned across
the six models below. Only the in-trade exit-decision block differs per
model. Where a model needs an indicator outside the locked StrategyParams
(an ATR-trail multiplier, an EMA period, a Chandelier lookback/multiplier),
a single plain, textbook-standard value is used and disclosed below rather
than searched for -- see the constants block.

Position sizing is pinned to the ORIGINAL stop distance (0.5x ATR, the
locked sl_atr_mult) for every model, so "R" means the same dollar amount in
every comparison and size_oz is identical across models for the same entry.
Only the live exit trigger -- not the size, not the entry -- is model-
specific. This is what "without changing entries" is taken to mean.

A model can specify its own target/stop, but every model still respects the
existing 12-bar max_holding_bars time-stop as a structural backstop (it caps
holding period, not profit) -- except Model E, which makes that backstop the
*only* exit rule, by design.

Run `python3 exit_models.py` to reproduce every number in EXIT_MODELS.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import CostModel, RiskModel, Trade, _initial_stop_tp
from data_loader import load_h1, load_m15
from indicators import ema
from metrics import annualized_sharpe, max_drawdown, summarize
from strategy import StrategyParams, generate_signals

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Plain, undisputed defaults -- not tuned, not searched. One value each.
ATR_TRAIL_MULT = 3.0       # Model B remainder trail: the common "3x ATR" trailing-stop convention
EMA_TRAIL_PERIOD = 20      # Model C: literally "EMA20" as named in the request
CHANDELIER_LOOKBACK = 22   # Model D: Chuck LeBeau's standard Chandelier Exit default
CHANDELIER_MULT = 3.0      # Model D: Chuck LeBeau's standard Chandelier Exit default

MODELS = ["current", "A", "B", "C", "D", "E"]
MODEL_LABELS = {
    "current": "Current exit (locked: SL 0.5x ATR, TP 4.5x ATR, 12-bar time stop)",
    "A": "Model A: TP=2R, SL=1R",
    "B": "Model B: 50% @ 1.5R -> breakeven -> trail remainder 3x ATR",
    "C": "Model C: EMA20 trailing exit",
    "D": "Model D: Chandelier exit (22, 3x ATR)",
    "E": "Model E: time stop only (12 bars, no price-based stop/target)",
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

    ema20 = ema(df["close"], EMA_TRAIL_PERIOD).to_numpy()
    hh = df["high"].rolling(CHANDELIER_LOOKBACK).max()
    ll = df["low"].rolling(CHANDELIER_LOOKBACK).min()
    # Lagged by one bar: a resting stop level must be fixed *before* the bar
    # whose range it is checked against, otherwise the bar's own high/low
    # would be used to set the very level being tested against that bar.
    chand_long = (hh - CHANDELIER_MULT * df["atr"]).shift(1).to_numpy()
    chand_short = (ll + CHANDELIER_MULT * df["atr"]).shift(1).to_numpy()

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

            if direction == "long":
                hit_orig_sl = lows[i] <= pos["orig_stop"]
            else:
                hit_orig_sl = highs[i] >= pos["orig_stop"]

            exit_reason = None
            exit_price = None
            slip = False
            closed_frac = 1.0  # fraction of ORIGINAL size closed by this event

            if model == "current":
                if direction == "long":
                    hit_tp = highs[i] >= pos["live_target"]
                else:
                    hit_tp = lows[i] <= pos["live_target"]
                if hit_orig_sl:
                    exit_reason, exit_price, slip = "stop_loss", pos["orig_stop"], True
                elif hit_tp:
                    exit_reason, exit_price, slip = "take_profit", pos["live_target"], False
                elif time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            elif model == "A":
                if direction == "long":
                    hit_tp = highs[i] >= pos["live_target"]
                else:
                    hit_tp = lows[i] <= pos["live_target"]
                if hit_orig_sl:
                    exit_reason, exit_price, slip = "stop_loss", pos["orig_stop"], True
                elif hit_tp:
                    exit_reason, exit_price, slip = "take_profit", pos["live_target"], False
                elif time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            elif model == "B":
                if not pos["partial_done"]:
                    if direction == "long":
                        hit_partial = highs[i] >= pos["partial_target"]
                    else:
                        hit_partial = lows[i] <= pos["partial_target"]
                    if hit_orig_sl:
                        exit_reason, exit_price, slip = "stop_loss", pos["orig_stop"], True
                    elif hit_partial:
                        # Book 50% at the exact 1.5R level (limit-style, no slippage),
                        # move the stop on the remainder to breakeven, start the trail.
                        leg_price = pos["partial_target"]
                        leg_fill = leg_price - costs.spread / 2 if direction == "long" else leg_price + costs.spread / 2
                        leg_pnl = (
                            (leg_fill - pos["entry_price"]) * pos["size_oz"] * 0.5
                            if direction == "long"
                            else (pos["entry_price"] - leg_fill) * pos["size_oz"] * 0.5
                        )
                        pos["realized_pnl"] += leg_pnl
                        equity += leg_pnl
                        pos["partial_done"] = True
                        pos["live_stop"] = pos["entry_price"]
                        pos["trail_anchor"] = pos["entry_price"]
                    elif time_stop:
                        exit_reason, exit_price, slip = "time_stop", closes[i], True
                else:
                    # Remainder: trail using ATR computed off the prior completed bar.
                    prior_atr = atrs[i - 1] if i > 0 else atrs[i]
                    prior_close = closes[i - 1] if i > 0 else closes[i]
                    if direction == "long":
                        candidate = prior_close - ATR_TRAIL_MULT * prior_atr
                        pos["live_stop"] = max(pos["live_stop"], candidate)
                        hit_trail = lows[i] <= pos["live_stop"]
                    else:
                        candidate = prior_close + ATR_TRAIL_MULT * prior_atr
                        pos["live_stop"] = min(pos["live_stop"], candidate)
                        hit_trail = highs[i] >= pos["live_stop"]
                    if hit_trail:
                        exit_reason, exit_price, slip, closed_frac = "atr_trail_stop", pos["live_stop"], True, 0.5
                    elif time_stop:
                        exit_reason, exit_price, slip, closed_frac = "time_stop", closes[i], True, 0.5

            elif model == "C":
                if direction == "long":
                    crossed = closes[i] < ema20[i]
                else:
                    crossed = closes[i] > ema20[i]
                if crossed:
                    exit_reason, exit_price, slip = "ema_cross", closes[i], False
                elif time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            elif model == "D":
                if direction == "long":
                    level = chand_long[i]
                    if not np.isnan(level):
                        pos["live_stop"] = max(pos["live_stop"], level)
                    hit_chand = lows[i] <= pos["live_stop"]
                else:
                    level = chand_short[i]
                    if not np.isnan(level):
                        pos["live_stop"] = min(pos["live_stop"], level)
                    hit_chand = highs[i] >= pos["live_stop"]
                if hit_chand:
                    exit_reason, exit_price, slip = "chandelier_stop", pos["live_stop"], True
                elif time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            elif model == "E":
                if time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            if exit_reason is not None:
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                if slip:
                    fill = fill - costs.stop_slippage if direction == "long" else fill + costs.stop_slippage
                leg_pnl = (
                    (fill - pos["entry_price"]) * pos["size_oz"] * closed_frac
                    if direction == "long"
                    else (pos["entry_price"] - fill) * pos["size_oz"] * closed_frac
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
                        entry_price=pos["entry_price"],
                        exit_price=fill,
                        stop_price=pos["orig_stop"],
                        take_profit=pos.get("live_target"),
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
                "stop_dist": stop_dist,
                "risk_dollars": risk_dollars,
                "size_oz": size_oz,
                "realized_pnl": 0.0,
                "partial_done": False,
            }
            if model == "current":
                pos["live_target"] = orig_target
            elif model == "A":
                pos["live_target"] = entry_price + 2 * stop_dist if direction == "long" else entry_price - 2 * stop_dist
            elif model == "B":
                pos["partial_target"] = (
                    entry_price + 1.5 * stop_dist if direction == "long" else entry_price - 1.5 * stop_dist
                )
            elif model == "D":
                init_level = chand_long[i] if direction == "long" else chand_short[i]
                pos["live_stop"] = init_level if not np.isnan(init_level) else orig_stop
            pending = None

        if pos is None and pending is None:
            if long_sig[i]:
                pending = "long"
            elif short_sig[i]:
                pending = "short"

    equity_curve_df = df[["time"]].copy()
    equity_curve_df["equity"] = equity_curve
    return rows, equity_curve_df


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()  # locked production defaults, unchanged
    costs = CostModel(spread=0.10, stop_slippage=0.03)  # tight-ECN, documented viable scenario
    risk = RiskModel()

    df = generate_signals(m15, h1, params)

    RESULTS_DIR.mkdir(exist_ok=True)
    summary_rows = []
    for model in MODELS:
        trades, eq_curve = simulate(model, df, params, costs, risk)
        stats = summarize(trades, eq_curve, risk.initial_equity)
        stats["model"] = model
        stats["label"] = MODEL_LABELS[model]
        summary_rows.append(stats)
        print(
            f"{model:8s} n={stats['total_trades']:5d} "
            f"wr={stats['win_rate']:.4f} pf={stats['profit_factor']:.4f} "
            f"exp_r={stats['expectancy_r']:.4f} avg_win=${stats['avg_win_usd']:.2f} "
            f"avg_loss=${stats['avg_loss_usd']:.2f} mdd={stats['max_drawdown_pct']:.2f}% "
            f"sharpe={stats['sharpe']:.3f}"
        )

    out = pd.DataFrame(summary_rows)
    out.to_csv(RESULTS_DIR / "exit_models_summary.csv", index=False)
    print(f"saved -> {RESULTS_DIR / 'exit_models_summary.csv'}")


if __name__ == "__main__":
    main()
