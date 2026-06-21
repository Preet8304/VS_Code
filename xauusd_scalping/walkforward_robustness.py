"""Walk-forward robustness validation of the proposed exit-management system:
current entry/SL unchanged, 25% TP at +1R, 25% TP at +2R, Chandelier trail on
the remaining 50% -- structurally identical to Model D in
strong_trend_stop_models.py, but run here against the FULL signal population
(every one of the 2,064 trades the locked strategy takes), not just the
Strong Trend regime subset that earlier file scoped down to. An optional
add-on variant also skips any entry whose signal-bar ATR percentile is above
70% -- the breakpoint STRONG_TREND_ANALYSIS.md found, offered here as a
secondary "with filter" comparison, never as the primary system.

This is a ROBUSTNESS study, not a search: no parameter here (partial sizes,
1R/2R trigger levels, Chandelier 22/3x, the 70% filter level) is tuned in
this file. The question being answered is whether Model D's improvement over
the current (unmanaged) exit holds up across time and execution conditions,
not whether some other configuration would do better.

Two disclosed deviations from the literal request, both forced by what the
data actually contains (`data_loader.load_m15()` returns 2012-05-15 through
2022-03-04 -- confirmed by direct query before writing this file):

1. Walk-forward split. Requested: 2015-2018 / 2019-2022 / 2023-2025. The
   2023-2025 window has zero data, and using the other two windows literally
   would silently discard the 194 trades that occur before 2015 (9.4% of the
   full population). Used instead, shifted back by one window so all
   available data is covered by three roughly-sequential, non-overlapping
   eras: 2012-2015 / 2016-2019 / 2020-2022 (last segment partial, ends
   2022-03-04 with the data, not Dec 2022).
2. Slippage sensitivity. CostModel.stop_slippage is a flat $ constant
   everywhere else in this project; "0.1 ATR / 0.2 ATR" is a *relative*
   quantity the existing model doesn't express. Implemented here as an
   override applied at the moment of any slipped fill (stop or time-stop):
   slip_amount = mult * atr_at_exit_bar, in place of the flat constant, only
   for this sensitivity test.

Cost-sensitivity baseline ("1x" anchor for the 0.5x/1x/1.5x/2x spread sweep)
is the ECN spread=0.10 used as the primary scenario in every prior round of
this project (regime_analysis.py, strong_trend_stop_models.py, etc.).

Run `python3 walkforward_robustness.py` to reproduce every number in
WALKFORWARD_ROBUSTNESS.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backtest import CostModel, RiskModel, Trade, _initial_stop_tp
from data_loader import load_h1, load_m15
from strategy import StrategyParams, generate_signals
from strong_trend_stop_models import (
    equity_curve_from_r,
    max_consecutive_losses,
    max_drawdown_pct,
    trades_to_df,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"

CHANDELIER_LOOKBACK = 22
CHANDELIER_MULT = 3.0
ATR_PCT_SKIP = 0.70

# Disclosed substitution for the data's actual coverage -- see module
# docstring point 1.
SEGMENTS = [
    ("2012-2015", "2012-01-01", "2016-01-01"),
    ("2016-2019", "2016-01-01", "2020-01-01"),
    ("2020-2022", "2020-01-01", "2023-01-01"),
]

BASE_SPREAD = 0.10
BASE_SLIPPAGE = 0.03
SPREAD_MULTS = [0.5, 1.0, 1.5, 2.0]
SLIPPAGE_ATR_MULTS = [0.0, 0.1, 0.2]


def simulate_baseline(df, params, costs, risk, atr_pct_filter=None, slippage_atr_mult=None):
    """Current exit, no stop management at all -- same entry/SL/target the
    locked strategy already uses. Same optional atr_pct_filter /
    slippage_atr_mult knobs as simulate_proposed for an apples-to-apples
    sensitivity comparison."""
    times = df["time"].to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    atrs = df["atr"].to_numpy()
    smas = df["sma"].to_numpy()
    atr_pct = df["atr_pct"].to_numpy()
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

            if direction == "long":
                hit_stop = lows[i] <= pos["orig_stop"]
                hit_target = highs[i] >= pos["orig_target"]
            else:
                hit_stop = highs[i] >= pos["orig_stop"]
                hit_target = lows[i] <= pos["orig_target"]

            exit_reason = exit_price = None
            slip = False
            if hit_stop:
                exit_reason, exit_price, slip = "stop_loss", pos["orig_stop"], True
            elif hit_target:
                exit_reason, exit_price = "take_profit", pos["orig_target"]
            elif time_stop:
                exit_reason, exit_price, slip = "time_stop", closes[i], True

            if exit_reason is not None:
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                if slip:
                    slip_amt = slippage_atr_mult * atrs[i] if slippage_atr_mult is not None else costs.stop_slippage
                    fill = fill - slip_amt if direction == "long" else fill + slip_amt
                pnl = ((fill - entry_price) if direction == "long" else (entry_price - fill)) * pos["size_oz"]
                equity += pnl
                r_multiple = pnl / pos["risk_dollars"] if pos["risk_dollars"] else 0.0
                rows.append(
                    Trade(
                        entry_time=pos["entry_time"], exit_time=times[i], direction=direction,
                        entry_price=entry_price, exit_price=fill, stop_price=pos["orig_stop"],
                        take_profit=pos["orig_target"], size_oz=pos["size_oz"], pnl=pnl,
                        r_multiple=r_multiple, exit_reason=exit_reason, bars_held=bars_held,
                    )
                )
                pos = None

        if pending is not None and pos is None:
            direction = pending
            entry_price = opens[i] + costs.spread / 2 if direction == "long" else opens[i] - costs.spread / 2
            sig_idx = i - 1 if i > 0 else i
            orig_stop, orig_target = _initial_stop_tp(direction, entry_price, atrs[sig_idx], smas[sig_idx], params)
            stop_dist = abs(entry_price - orig_stop)
            risk_dollars = equity * risk.risk_per_trade
            size_oz = risk_dollars / stop_dist if stop_dist > 0 else 0.0
            pos = {
                "direction": direction, "entry_time": times[i], "entry_index": i, "entry_price": entry_price,
                "orig_stop": orig_stop, "orig_target": orig_target, "risk_dollars": risk_dollars, "size_oz": size_oz,
            }
            pending = None

        if pos is None and pending is None:
            if long_sig[i] and (atr_pct_filter is None or atr_pct[i] <= atr_pct_filter):
                pending = "long"
            elif short_sig[i] and (atr_pct_filter is None or atr_pct[i] <= atr_pct_filter):
                pending = "short"

    return rows


def simulate_proposed(df, params, costs, risk, chand_long, chand_short, atr_pct_filter=None, slippage_atr_mult=None):
    """25% @ +1R, 25% @ +2R, trail remaining 50% with a Chandelier exit
    (22, 3x ATR). Identical structure to Model D in
    strong_trend_stop_models.py, generalized with the same optional
    atr_pct_filter / slippage_atr_mult knobs as simulate_baseline above."""
    times = df["time"].to_numpy()
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    atrs = df["atr"].to_numpy()
    smas = df["sma"].to_numpy()
    atr_pct = df["atr_pct"].to_numpy()
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

            if pos["stage"] == "trailing":
                level = chand_long[i] if direction == "long" else chand_short[i]
                if not np.isnan(level):
                    pos["live_stop"] = max(pos["live_stop"], level) if direction == "long" else min(pos["live_stop"], level)

            if direction == "long":
                hit_stop = lows[i] <= pos["live_stop"]
                hit_target = pos["target_active"] and highs[i] >= pos["live_target"]
            else:
                hit_stop = highs[i] >= pos["live_stop"]
                hit_target = pos["target_active"] and lows[i] <= pos["live_target"]

            exit_reason = exit_price = None
            slip = False

            if hit_stop:
                exit_reason, exit_price, slip = pos["stop_label"], pos["live_stop"], True
            elif hit_target:
                exit_reason, exit_price = "take_profit", pos["live_target"]
            else:
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

                if time_stop:
                    exit_reason, exit_price, slip = "time_stop", closes[i], True

            if exit_reason is not None:
                closed_frac = pos["remaining_frac"]
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                if slip:
                    slip_amt = slippage_atr_mult * atrs[i] if slippage_atr_mult is not None else costs.stop_slippage
                    fill = fill - slip_amt if direction == "long" else fill + slip_amt
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
            orig_stop, orig_target = _initial_stop_tp(direction, entry_price, atrs[sig_idx], smas[sig_idx], params)
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
            if long_sig[i] and (atr_pct_filter is None or atr_pct[i] <= atr_pct_filter):
                pending = "long"
            elif short_sig[i] and (atr_pct_filter is None or atr_pct[i] <= atr_pct_filter):
                pending = "short"

    return rows


def sharpe_from_r(tdf: pd.DataFrame, risk: RiskModel) -> float:
    if len(tdf) < 2:
        return 0.0
    equity = equity_curve_from_r(tdf["r_multiple"], risk.initial_equity, risk.risk_per_trade)
    ec = pd.DataFrame({"time": pd.to_datetime(tdf["exit_time"]).to_numpy(), "equity": equity.to_numpy()})
    daily = ec.set_index("time")["equity"].resample("1D").last().ffill()
    daily_returns = daily.pct_change().dropna()
    if daily_returns.std() == 0 or len(daily_returns) < 2:
        return 0.0
    return float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))


def full_stats(tdf: pd.DataFrame, risk: RiskModel) -> dict:
    n = len(tdf)
    if n == 0:
        return {
            "trades": 0, "win_rate": 0.0, "profit_factor": float("nan"), "expectancy_r": 0.0,
            "max_drawdown_pct": 0.0, "sharpe": 0.0, "max_consec_losses": 0, "cagr_pct": float("nan"),
        }
    r = tdf["r_multiple"]
    wins = r[r > 0]
    losses = r[r <= 0]
    gp = wins.sum()
    gl = -losses.sum()
    equity = equity_curve_from_r(r, risk.initial_equity, risk.risk_per_trade)
    entry_times = pd.to_datetime(tdf["entry_time"])
    exit_times = pd.to_datetime(tdf["exit_time"])
    years = (exit_times.iloc[-1] - entry_times.iloc[0]).days / 365.25
    final_equity = equity.iloc[-1]
    cagr = (final_equity / risk.initial_equity) ** (1 / years) - 1 if years > 0 else float("nan")
    return {
        "trades": n,
        "win_rate": len(wins) / n,
        "profit_factor": gp / gl if gl > 0 else float("inf"),
        "expectancy_r": r.mean(),
        "max_drawdown_pct": max_drawdown_pct(r, risk.initial_equity, risk.risk_per_trade) * 100,
        "sharpe": sharpe_from_r(tdf, risk),
        "max_consec_losses": max_consecutive_losses(r),
        "cagr_pct": cagr * 100,
    }


def segment_table(tdf: pd.DataFrame, risk: RiskModel) -> pd.DataFrame:
    rows = []
    entry_times = pd.to_datetime(tdf["entry_time"])
    for label, start, end in SEGMENTS:
        mask = (entry_times >= start) & (entry_times < end)
        stats = full_stats(tdf[mask], risk)
        stats["segment"] = label
        rows.append(stats)
    return pd.DataFrame(rows)


def leave_one_year_out(tdf: pd.DataFrame, risk: RiskModel) -> pd.DataFrame:
    years = sorted(pd.to_datetime(tdf["entry_time"]).dt.year.unique())
    full = full_stats(tdf, risk)
    rows = [{**full, "year_removed": "none (full population)"}]
    for yr in years:
        mask = pd.to_datetime(tdf["entry_time"]).dt.year != yr
        stats = full_stats(tdf[mask], risk)
        stats["year_removed"] = yr
        rows.append(stats)
    return pd.DataFrame(rows)


def monte_carlo(tdf: pd.DataFrame, risk: RiskModel, n_runs: int = 1000, seed: int = 42) -> dict:
    r = tdf["r_multiple"].to_numpy()
    n = len(r)
    entry_times = pd.to_datetime(tdf["entry_time"])
    exit_times = pd.to_datetime(tdf["exit_time"])
    years = (exit_times.iloc[-1] - entry_times.iloc[0]).days / 365.25
    rng = np.random.default_rng(seed)
    cagrs = np.empty(n_runs)
    max_dds = np.empty(n_runs)
    for k in range(n_runs):
        rr = rng.permutation(r)
        equity = risk.initial_equity * np.cumprod(1.0 + rr * risk.risk_per_trade)
        running_max = np.maximum.accumulate(equity)
        dd = (equity - running_max) / running_max
        max_dds[k] = dd.min()
        cagrs[k] = (equity[-1] / risk.initial_equity) ** (1 / years) - 1 if years > 0 else np.nan

    return {
        "n_runs": n_runs,
        "median_cagr_pct": float(np.median(cagrs)) * 100,
        "min_cagr_pct": float(np.min(cagrs)) * 100,
        "max_cagr_pct": float(np.max(cagrs)) * 100,
        "median_drawdown_pct": float(np.median(max_dds)) * 100,
        "p95_worst_drawdown_pct": float(np.percentile(max_dds, 5)) * 100,
        "prob_ruin_30pct": float((max_dds <= -0.30).mean()),
        "prob_ruin_50pct": float((max_dds <= -0.50).mean()),
    }


def cost_sensitivity(df, params, risk, chand_long, chand_short, simulate_fn, **kwargs) -> pd.DataFrame:
    rows = []
    for mult in SPREAD_MULTS:
        costs = CostModel(spread=BASE_SPREAD * mult, stop_slippage=BASE_SLIPPAGE)
        if simulate_fn is simulate_proposed:
            trades = simulate_fn(df, params, costs, risk, chand_long, chand_short, **kwargs)
        else:
            trades = simulate_fn(df, params, costs, risk, **kwargs)
        stats = full_stats(trades_to_df(trades), risk)
        stats["spread_mult"] = mult
        stats["spread_value"] = BASE_SPREAD * mult
        rows.append(stats)
    return pd.DataFrame(rows)


def slippage_sensitivity(df, params, risk, chand_long, chand_short, simulate_fn, **kwargs) -> pd.DataFrame:
    rows = []
    for atr_mult in SLIPPAGE_ATR_MULTS:
        costs = CostModel(spread=BASE_SPREAD, stop_slippage=BASE_SLIPPAGE)
        if simulate_fn is simulate_proposed:
            trades = simulate_fn(df, params, costs, risk, chand_long, chand_short, slippage_atr_mult=atr_mult, **kwargs)
        else:
            trades = simulate_fn(df, params, costs, risk, slippage_atr_mult=atr_mult, **kwargs)
        stats = full_stats(trades_to_df(trades), risk)
        stats["slippage_atr_mult"] = atr_mult
        rows.append(stats)
    return pd.DataFrame(rows)


def print_stats(prefix: str, stats: dict) -> None:
    print(
        f"{prefix:28s} n={stats['trades']:4d} wr={stats['win_rate']:.4f} "
        f"pf={stats['profit_factor']:.4f} exp_r={stats['expectancy_r']:.4f} "
        f"mdd={stats['max_drawdown_pct']:.2f}% sharpe={stats['sharpe']:.3f} "
        f"max_consec_loss={stats['max_consec_losses']} cagr={stats['cagr_pct']:.2f}%"
    )


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()
    risk = RiskModel()
    base_costs = CostModel(spread=BASE_SPREAD, stop_slippage=BASE_SLIPPAGE)

    print(f"data range: {m15['time'].min()} -> {m15['time'].max()}")

    df = generate_signals(m15, h1, params)
    hh = df["high"].rolling(CHANDELIER_LOOKBACK).max()
    ll = df["low"].rolling(CHANDELIER_LOOKBACK).min()
    chand_long = (hh - CHANDELIER_MULT * df["atr"]).shift(1).to_numpy()
    chand_short = (ll + CHANDELIER_MULT * df["atr"]).shift(1).to_numpy()

    RESULTS_DIR.mkdir(exist_ok=True)

    variants = {
        "current": trades_to_df(simulate_baseline(df, params, base_costs, risk)),
        "proposed": trades_to_df(simulate_proposed(df, params, base_costs, risk, chand_long, chand_short)),
        "proposed_filtered": trades_to_df(
            simulate_proposed(df, params, base_costs, risk, chand_long, chand_short, atr_pct_filter=ATR_PCT_SKIP)
        ),
    }

    print("\n--- Full-period headline (sanity check vs prior rounds) ---")
    for name, tdf in variants.items():
        print_stats(name, full_stats(tdf, risk))

    print("\n--- Walk-forward segments ---")
    seg_frames = []
    for name, tdf in variants.items():
        seg = segment_table(tdf, risk)
        seg["variant"] = name
        seg_frames.append(seg)
        print(f"[{name}]")
        for _, row in seg.iterrows():
            print_stats(row["segment"], row.to_dict())
    pd.concat(seg_frames, ignore_index=True).to_csv(RESULTS_DIR / "wf_segments.csv", index=False)

    print("\n--- Leave-one-year-out ---")
    loyo_frames = []
    for name, tdf in variants.items():
        loyo = leave_one_year_out(tdf, risk)
        loyo["variant"] = name
        loyo_frames.append(loyo)
        print(f"[{name}]")
        for _, row in loyo.iterrows():
            print_stats(f"remove {row['year_removed']}", row.to_dict())
    pd.concat(loyo_frames, ignore_index=True).to_csv(RESULTS_DIR / "wf_leave_one_year_out.csv", index=False)

    print("\n--- Monte Carlo (1000 trade-order shuffles) ---")
    mc_rows = []
    for name, tdf in variants.items():
        mc = monte_carlo(tdf, risk)
        mc["variant"] = name
        mc_rows.append(mc)
        print(f"{name:20s} {mc}")
    pd.DataFrame(mc_rows).to_csv(RESULTS_DIR / "wf_monte_carlo.csv", index=False)

    print("\n--- Cost sensitivity (spread multiplier, base=0.10) ---")
    cost_frames = []
    for name, simulate_fn, extra in [
        ("current", simulate_baseline, {}),
        ("proposed", simulate_proposed, {"chand_long": chand_long, "chand_short": chand_short}),
        ("proposed_filtered", simulate_proposed, {"chand_long": chand_long, "chand_short": chand_short, "atr_pct_filter": ATR_PCT_SKIP}),
    ]:
        if simulate_fn is simulate_proposed:
            cl, cs = extra.pop("chand_long"), extra.pop("chand_short")
            cs_tab = cost_sensitivity(df, params, risk, cl, cs, simulate_fn, **extra)
        else:
            cs_tab = cost_sensitivity(df, params, risk, None, None, simulate_fn, **extra)
        cs_tab["variant"] = name
        cost_frames.append(cs_tab)
        print(f"[{name}]")
        for _, row in cs_tab.iterrows():
            print_stats(f"spread x{row['spread_mult']}", row.to_dict())
    pd.concat(cost_frames, ignore_index=True).to_csv(RESULTS_DIR / "wf_cost_sensitivity.csv", index=False)

    print("\n--- Slippage sensitivity (0 / 0.1 / 0.2 x ATR at exit) ---")
    slip_frames = []
    for name, simulate_fn, extra in [
        ("current", simulate_baseline, {}),
        ("proposed", simulate_proposed, {"chand_long": chand_long, "chand_short": chand_short}),
        ("proposed_filtered", simulate_proposed, {"chand_long": chand_long, "chand_short": chand_short, "atr_pct_filter": ATR_PCT_SKIP}),
    ]:
        if simulate_fn is simulate_proposed:
            cl, cs = extra.pop("chand_long"), extra.pop("chand_short")
            sl_tab = slippage_sensitivity(df, params, risk, cl, cs, simulate_fn, **extra)
        else:
            sl_tab = slippage_sensitivity(df, params, risk, None, None, simulate_fn, **extra)
        sl_tab["variant"] = name
        slip_frames.append(sl_tab)
        print(f"[{name}]")
        for _, row in sl_tab.iterrows():
            print_stats(f"slip {row['slippage_atr_mult']}xATR", row.to_dict())
    pd.concat(slip_frames, ignore_index=True).to_csv(RESULTS_DIR / "wf_slippage_sensitivity.csv", index=False)

    for name, tdf in variants.items():
        tdf.to_csv(RESULTS_DIR / f"wf_trades_{name}.csv", index=False)

    print(f"\nsaved all tables -> {RESULTS_DIR}")


if __name__ == "__main__":
    main()
