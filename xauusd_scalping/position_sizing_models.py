"""Position-sizing comparison. Entries, exits, and stops are UNCHANGED --
this file varies only the risk fraction applied per trade.

Because the locked strategy's stop-loss distance is fixed per trade and
size_oz = risk_dollars / stop_dist, every trade's r_multiple = pnl /
risk_dollars is mathematically independent of position sizing (risk_dollars
and size_oz cancel out of that ratio). So no bar-by-bar backtest replay is
needed here: this script reuses the already-validated, chronologically
sorted 2,064-trade r_multiple sequence in
results/trade_regime_full_ecn.csv (full signal population, ECN costs) and
reconstructs a dollar equity curve per sizing model via
equity *= (1 + r_multiple * risk_fraction(...)).

Eight sizing models compared, none tuned beyond the plain, disclosed
choices below ("Do not optimize" -- this is a comparison of archetypes,
not a parameter search):

  - Fixed fractional: 0.25% / 0.5% / 1% of current equity, every trade.
  - Volatility-adjusted: base 0.5%, scaled by
    (sample median atr_pct_sig) / (this trade's atr_pct_sig), clipped to
    [0.5x, 1.5x] of base -- larger size in calm conditions, smaller in
    volatile ones. Median (0.56) and clip band are plain, disclosed
    constants, not fit to the data beyond using its own median as the
    calibration anchor.
  - Fractional Kelly: 0.25x and 0.5x of the full-sample Kelly fraction
    f* = p - (1-p)/b, computed once from all 2,064 trades (p = win rate,
    b = avg_win_R / avg_loss_R). Disclosed limitation: this is a static,
    full-sample (look-ahead) estimate, not a walk-forward-safe one --
    appropriate for comparing sizing archetypes, not a live-deployment
    claim.
  - Anti-Martingale: base 0.5%, 1.5x base (0.75%) on any trade entered
    while equity is at an all-time high (no open drawdown), base
    otherwise.
  - Drawdown-aware: base 0.5%, cut 50% (to 0.25%) once 5 consecutive
    losses have occurred, restored to base the instant a winning trade
    resets the consecutive-loss counter.

Monte Carlo path-dependence note (the reason two separate MC code paths
exist below): fixed-fractional / vol-adjusted / Kelly each set risk_
fraction from a trade's OWN fixed attributes (a constant, or that trade's
own atr_pct_sig) -- so under any reordering, each trade still carries the
same (r_multiple, risk_fraction) pair, and final compounded equity is the
product of the same set of (1 + r*f) factors regardless of order
(multiplication commutes). CAGR is therefore mathematically invariant to
shuffling for those six models -- confirmed below via cagr_std_pct. Path-
shaped statistics (max drawdown) still vary by shuffle order even for
those six, because they depend on the sequence, not just the final value.
Anti-Martingale and Drawdown-aware are different: their risk_fraction
depends on running state (the equity peak / the consecutive-loss streak)
that is itself a product of trade order, so reshuffling changes which
risk fraction lands on which R-multiple -- CAGR genuinely varies for these
two as well.

Sharpe / Ulcer Index / longest-recovery-period are calendar-time concepts
(computed on a daily-resampled equity curve, the same resample('1D')
convention metrics.py / walkforward_robustness.py already use for
Sharpe). They are reported once on the real chronological trade sequence
in each model's headline row -- NOT recomputed inside the Monte Carlo
loop, because a reshuffled trade order has no genuine calendar-day
structure (trades keep their original timestamps; reordering them
produces an artifact sequence with duplicated/out-of-order dates, not a
coherent calendar history). Monte Carlo here reports CAGR and max-
drawdown distributions only, the same convention walkforward_robustness.py's
Monte Carlo section already used.

Run `python3 position_sizing_models.py` to reproduce every number in
POSITION_SIZING.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent / "results"

INITIAL_EQUITY = 10_000.0  # same convention as backtest.py RiskModel

FIXED_LEVELS = [0.0025, 0.005, 0.01]
VOL_BASE = 0.005
VOL_CLIP = (0.5, 1.5)
KELLY_FRACTIONS = {"kelly_0.25": 0.25, "kelly_0.5": 0.5}
ANTI_MARTINGALE_BASE = 0.005
ANTI_MARTINGALE_MULT = 1.5
DRAWDOWN_AWARE_BASE = 0.005
DRAWDOWN_AWARE_LOSS_STREAK = 5
DRAWDOWN_AWARE_CUT = 0.5

N_MC_RUNS = 1000
MC_SEED = 42

MODEL_LABELS = {
    "fixed_0.25pct": "Fixed fractional 0.25%",
    "fixed_0.5pct": "Fixed fractional 0.5%",
    "fixed_1pct": "Fixed fractional 1%",
    "vol_adjusted": "Volatility-adjusted (base 0.5%, x[0.5,1.5])",
    "kelly_0.25": "Fractional Kelly 0.25x",
    "kelly_0.5": "Fractional Kelly 0.5x",
    "anti_martingale": "Anti-Martingale (base 0.5%, 1.5x at equity highs)",
    "drawdown_aware": "Drawdown-aware (base 0.5%, -50% after 5 losses)",
}


def full_sample_kelly(r: np.ndarray) -> dict:
    wins = r[r > 0]
    losses = r[r <= 0]
    p = len(wins) / len(r)
    avg_win = float(wins.mean())
    avg_loss = float(-losses.mean())
    b = avg_win / avg_loss
    f_star = p - (1 - p) / b
    return {"p": p, "avg_win_r": avg_win, "avg_loss_r": avg_loss, "b": b, "kelly_full": f_star}


def stateless_risk_arrays(r: np.ndarray, atr_pct_sig: np.ndarray, kelly_full: float) -> dict[str, np.ndarray]:
    n = len(r)
    arrays = {}
    for level in FIXED_LEVELS:
        name = f"fixed_{level * 100:g}pct"
        arrays[name] = np.full(n, level)
    med_atr = np.median(atr_pct_sig)
    mult = np.clip(med_atr / atr_pct_sig, VOL_CLIP[0], VOL_CLIP[1])
    arrays["vol_adjusted"] = VOL_BASE * mult
    for name, frac in KELLY_FRACTIONS.items():
        arrays[name] = np.full(n, frac * kelly_full)
    return arrays


def equity_path_from_risk(r: np.ndarray, risk_arr: np.ndarray, initial_equity: float) -> np.ndarray:
    return initial_equity * np.cumprod(1.0 + r * risk_arr)


def replay_stateful(model: str, r: np.ndarray, initial_equity: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(r)
    equity = initial_equity
    peak = initial_equity
    consec_losses = 0
    equity_path = np.empty(n)
    risk_path = np.empty(n)
    for i in range(n):
        if model == "anti_martingale":
            rf = ANTI_MARTINGALE_BASE * ANTI_MARTINGALE_MULT if equity >= peak else ANTI_MARTINGALE_BASE
        elif model == "drawdown_aware":
            rf = (
                DRAWDOWN_AWARE_BASE * DRAWDOWN_AWARE_CUT
                if consec_losses >= DRAWDOWN_AWARE_LOSS_STREAK
                else DRAWDOWN_AWARE_BASE
            )
        else:
            raise ValueError(model)
        risk_path[i] = rf
        equity = equity * (1.0 + r[i] * rf)
        equity_path[i] = equity
        peak = max(peak, equity)
        consec_losses = consec_losses + 1 if r[i] <= 0 else 0
    return equity_path, risk_path


def max_drawdown_pct_from_equity(equity: np.ndarray) -> float:
    running_max = np.maximum.accumulate(equity)
    dd = (equity - running_max) / running_max
    return float(dd.min()) if len(dd) else 0.0


def daily_equity_curve(equity_path: np.ndarray, exit_times: np.ndarray) -> pd.Series:
    ec = pd.Series(equity_path, index=pd.to_datetime(exit_times))
    return ec.resample("1D").last().ffill()


def sharpe_from_daily(daily: pd.Series) -> float:
    daily_returns = daily.pct_change().dropna()
    if len(daily_returns) < 2 or daily_returns.std() == 0:
        return 0.0
    return float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))


def ulcer_index_from_daily(daily: pd.Series) -> float:
    running_max = daily.cummax()
    dd_pct = (daily - running_max) / running_max * 100
    return float(np.sqrt((dd_pct ** 2).mean()))


def drawdown_episodes(daily: pd.Series) -> tuple[list[tuple], int, int | None]:
    """Returns (completed episodes, longest completed duration in days,
    still-open unrecovered duration in days or None if the series ends at
    a new high)."""
    peak = daily.iloc[0]
    peak_date = daily.index[0]
    episodes = []
    in_dd = False
    dd_start = None
    for date, eq in daily.items():
        if eq >= peak:
            if in_dd:
                episodes.append((dd_start, date, (date - dd_start).days))
                in_dd = False
            peak = eq
            peak_date = date
        else:
            if not in_dd:
                in_dd = True
                dd_start = peak_date
    still_open = (daily.index[-1] - dd_start).days if in_dd else None
    longest_completed = max((d for _, _, d in episodes), default=0)
    return episodes, longest_completed, still_open


def model_stats(name: str, equity_path: np.ndarray, entry_times: np.ndarray, exit_times: np.ndarray,
                 initial_equity: float) -> dict:
    years = (pd.Timestamp(exit_times[-1]) - pd.Timestamp(entry_times[0])).days / 365.25
    final_equity = float(equity_path[-1])
    cagr = (final_equity / initial_equity) ** (1 / years) - 1 if years > 0 else float("nan")
    mdd = max_drawdown_pct_from_equity(equity_path)
    daily = daily_equity_curve(equity_path, exit_times)
    sharpe = sharpe_from_daily(daily)
    ulcer = ulcer_index_from_daily(daily)
    _, longest_completed, still_open = drawdown_episodes(daily)
    mdd_pct = mdd * 100
    cagr_pct = cagr * 100
    mar = cagr_pct / abs(mdd_pct) if mdd_pct != 0 else float("inf")
    return {
        "model": name,
        "final_equity": final_equity,
        "cagr_pct": cagr_pct,
        "max_drawdown_pct": mdd_pct,
        "ulcer_index": ulcer,
        "sharpe": sharpe,
        "mar_ratio": mar,
        "longest_recovery_days": longest_completed,
        "still_in_drawdown": still_open is not None,
        "current_unrecovered_days": still_open if still_open is not None else 0,
    }


def summarize_mc(cagrs: np.ndarray, mdds: np.ndarray, n_runs: int) -> dict:
    return {
        "n_runs": n_runs,
        "median_cagr_pct": float(np.median(cagrs)) * 100,
        "min_cagr_pct": float(np.min(cagrs)) * 100,
        "max_cagr_pct": float(np.max(cagrs)) * 100,
        "cagr_std_pct": float(np.std(cagrs)) * 100,
        "median_drawdown_pct": float(np.median(mdds)) * 100,
        "p95_worst_drawdown_pct": float(np.percentile(mdds, 5)) * 100,
        "prob_ruin_30pct": float((mdds <= -0.30).mean()),
        "prob_ruin_50pct": float((mdds <= -0.50).mean()),
    }


def monte_carlo_stateless(r: np.ndarray, risk_arr: np.ndarray, initial_equity: float, years: float,
                           n_runs: int = N_MC_RUNS, seed: int = MC_SEED) -> dict:
    n = len(r)
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    cagrs = np.empty(n_runs)
    mdds = np.empty(n_runs)
    for k in range(n_runs):
        perm = rng.permutation(idx)
        rr = r[perm]
        ff = risk_arr[perm]
        equity = initial_equity * np.cumprod(1.0 + rr * ff)
        running_max = np.maximum.accumulate(equity)
        dd = (equity - running_max) / running_max
        mdds[k] = dd.min()
        cagrs[k] = (equity[-1] / initial_equity) ** (1 / years) - 1 if years > 0 else np.nan
    return summarize_mc(cagrs, mdds, n_runs)


def monte_carlo_stateful(model: str, r: np.ndarray, initial_equity: float, years: float,
                          n_runs: int = N_MC_RUNS, seed: int = MC_SEED) -> dict:
    n = len(r)
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    cagrs = np.empty(n_runs)
    mdds = np.empty(n_runs)
    for k in range(n_runs):
        perm = rng.permutation(idx)
        rr = r[perm]
        equity_path, _ = replay_stateful(model, rr, initial_equity)
        running_max = np.maximum.accumulate(equity_path)
        dd = (equity_path - running_max) / running_max
        mdds[k] = dd.min()
        cagrs[k] = (equity_path[-1] / initial_equity) ** (1 / years) - 1 if years > 0 else np.nan
    return summarize_mc(cagrs, mdds, n_runs)


def print_row(stats: dict) -> None:
    print(
        f"{stats['model']:16s} final=${stats['final_equity']:>12,.0f} "
        f"cagr={stats['cagr_pct']:7.2f}% mdd={stats['max_drawdown_pct']:7.2f}% "
        f"ulcer={stats['ulcer_index']:6.2f} sharpe={stats['sharpe']:6.3f} "
        f"mar={stats['mar_ratio']:6.2f} recovery={stats['longest_recovery_days']:5d}d "
        f"{'STILL OPEN ' + str(stats['current_unrecovered_days']) + 'd' if stats['still_in_drawdown'] else ''}"
    )


def main() -> None:
    path = RESULTS_DIR / "trade_regime_full_ecn.csv"
    df = pd.read_csv(path, parse_dates=["entry_time", "exit_time"])
    assert df["entry_time"].is_monotonic_increasing, "expected chronologically sorted trade list"

    r = df["r_multiple"].to_numpy()
    atr_pct_sig = df["atr_pct_sig"].to_numpy()
    entry_times = df["entry_time"].to_numpy()
    exit_times = df["exit_time"].to_numpy()
    n = len(df)
    years = (pd.Timestamp(exit_times[-1]) - pd.Timestamp(entry_times[0])).days / 365.25

    print(f"loaded {n} trades, {pd.Timestamp(entry_times[0])} -> {pd.Timestamp(exit_times[-1])} ({years:.2f} years)")

    kelly = full_sample_kelly(r)
    print(
        f"full-sample Kelly: p={kelly['p']:.5f} avg_win_r={kelly['avg_win_r']:.5f} "
        f"avg_loss_r={kelly['avg_loss_r']:.5f} b={kelly['b']:.5f} f*={kelly['kelly_full']:.5f} "
        f"(0.25x={0.25 * kelly['kelly_full']:.5f}, 0.5x={0.5 * kelly['kelly_full']:.5f})"
    )
    print(f"atr_pct_sig median used for vol-adjusted calibration: {np.median(atr_pct_sig):.5f}")

    stateless = stateless_risk_arrays(r, atr_pct_sig, kelly["kelly_full"])

    RESULTS_DIR.mkdir(exist_ok=True)

    results = []
    equity_paths = {}
    print("\n--- Headline per-model stats (real chronological order) ---")
    for name, risk_arr in stateless.items():
        eq = equity_path_from_risk(r, risk_arr, INITIAL_EQUITY)
        equity_paths[name] = eq
        stats = model_stats(name, eq, entry_times, exit_times, INITIAL_EQUITY)
        results.append(stats)
        print_row(stats)

    for name in ["anti_martingale", "drawdown_aware"]:
        eq, _ = replay_stateful(name, r, INITIAL_EQUITY)
        equity_paths[name] = eq
        stats = model_stats(name, eq, entry_times, exit_times, INITIAL_EQUITY)
        results.append(stats)
        print_row(stats)

    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULTS_DIR / "position_sizing_models.csv", index=False)

    print(f"\n--- Monte Carlo ({N_MC_RUNS} trade-order shuffles per model) ---")
    mc_rows = []
    for name, risk_arr in stateless.items():
        mc = monte_carlo_stateless(r, risk_arr, INITIAL_EQUITY, years)
        mc["model"] = name
        mc_rows.append(mc)
        print(f"{name:16s} {mc}")
    for name in ["anti_martingale", "drawdown_aware"]:
        mc = monte_carlo_stateful(name, r, INITIAL_EQUITY, years)
        mc["model"] = name
        mc_rows.append(mc)
        print(f"{name:16s} {mc}")

    mc_df = pd.DataFrame(mc_rows)
    mc_df.to_csv(RESULTS_DIR / "position_sizing_monte_carlo.csv", index=False)

    eq_df = pd.DataFrame(equity_paths)
    eq_df.insert(0, "exit_time", exit_times)
    eq_df.to_csv(RESULTS_DIR / "position_sizing_equity_paths.csv", index=False)

    print(f"\nsaved all tables -> {RESULTS_DIR}")


if __name__ == "__main__":
    main()
