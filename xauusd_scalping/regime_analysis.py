"""Classify every trade in the locked strategy by entry-bar market regime.

Read-only research tool. Reuses audit.run_audit() verbatim for the trade
list (entries, exits, MFE/MAE in R -- nothing about the strategy or backtest
is touched), then attaches three regime inputs computed at the SIGNAL bar
(one bar before entry, same no-lookahead convention as every other entry-
context field in audit.py):

  * ADX(14)        -- standard Wilder trend-strength indicator, period 14 to
                       match the project's existing atr_period (not a new
                       tunable). Classic, undisputed convention: ADX >= 25 is
                       "trending," below is "non-trending."
  * ATR percentile -- the strategy's own existing `atr_pct` field
                       (atr_lookback=100, already in StrategyParams).
                       Split at the median (0.5) to call "quiet" vs.
                       "volatile" -- the plainest possible split of an
                       existing field, not a new threshold search.
  * EMA50 slope    -- the project's existing ema() helper, span=50 (an
                       existing constant: StrategyParams.htf_ema_fast is 50
                       on H1; this uses the same period directly on M15 for
                       a same-timeframe slope reading), expressed in ATR
                       units over a 14-bar lookback (matching the ADX/ATR
                       period, not a separately invented window). Reported
                       descriptively per regime, not used as a classifying
                       threshold -- the four named regimes are a 2x2 grid of
                       ADX x ATR-percentile only, since the four requested
                       regime names ("Quiet/Strong Trend", "Quiet/Volatile
                       Range") name exactly two axes.

Run `python3 regime_analysis.py` to reproduce every number in
REGIME_ANALYSIS.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from audit import run_audit
from backtest import CostModel, RiskModel
from data_loader import load_h1, load_m15
from indicators import ema, true_range
from strategy import StrategyParams, generate_signals

RESULTS_DIR = Path(__file__).resolve().parent / "results"
ADX_PERIOD = 14          # matches the existing atr_period, not a new tunable
ADX_TREND_THRESHOLD = 25  # Wilder's own classic trend/non-trend split
SLOPE_LOOKBACK = 14       # matches ADX_PERIOD/atr_period


def compute_adx(df: pd.DataFrame, period: int = ADX_PERIOD) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = true_range(high, low, close)

    smoothed_tr = tr.ewm(alpha=1 / period, adjust=False).mean()
    smoothed_plus_dm = pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean()
    smoothed_minus_dm = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * smoothed_plus_dm / smoothed_tr.replace(0.0, np.nan)
    minus_di = 100 * smoothed_minus_dm / smoothed_tr.replace(0.0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx.fillna(0.0)


def classify_regime(adx_sig: float, atr_pct_sig: float) -> str:
    trending = adx_sig >= ADX_TREND_THRESHOLD
    volatile = atr_pct_sig >= 0.5
    if trending and not volatile:
        return "Quiet Trend"
    if trending and volatile:
        return "Strong Trend"
    if not trending and not volatile:
        return "Quiet Range"
    return "Volatile Range"


def build_regime_table(m15: pd.DataFrame, h1: pd.DataFrame, params: StrategyParams, costs: CostModel, risk: RiskModel) -> pd.DataFrame:
    df = generate_signals(m15, h1, params)
    df["adx"] = compute_adx(df)
    ema50 = ema(df["close"], 50)
    df["ema50_slope_atr"] = (ema50 - ema50.shift(SLOPE_LOOKBACK)) / df["atr"]

    trades = run_audit(m15, h1, params, costs, risk)

    regime_at_entry = pd.DataFrame(
        {
            "time": df["time"],
            "adx_sig": df["adx"].shift(1),
            "atr_pct_sig": df["atr_pct"].shift(1),
            "ema50_slope_sig": df["ema50_slope_atr"].shift(1),
        }
    )
    merged = trades.merge(regime_at_entry, left_on="entry_time", right_on="time", how="left")
    merged["regime"] = [
        classify_regime(a, p) for a, p in zip(merged["adx_sig"], merged["atr_pct_sig"])
    ]
    return merged


def summarize_regime(group: pd.DataFrame) -> dict:
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
        "expectancy_usd": group["pnl"].mean() if n else 0.0,
        "avg_mae_r": group["mae_r"].mean() if n else 0.0,
        "avg_mfe_r": group["mfe_r"].mean() if n else 0.0,
        "avg_adx": group["adx_sig"].mean() if n else 0.0,
        "avg_atr_pct": group["atr_pct_sig"].mean() if n else 0.0,
        "avg_ema50_slope_atr": group["ema50_slope_sig"].mean() if n else 0.0,
        "loss_count": len(losses),
        "loss_dollars": float(-losses["pnl"].sum()) if n else 0.0,
    }


def main() -> None:
    m15 = load_m15()
    h1 = load_h1()
    params = StrategyParams()
    costs = CostModel(spread=0.10, stop_slippage=0.03)
    risk = RiskModel()

    merged = build_regime_table(m15, h1, params, costs, risk)

    RESULTS_DIR.mkdir(exist_ok=True)
    merged.to_csv(RESULTS_DIR / "trade_regime_full_ecn.csv", index=False)

    rows = []
    for regime in ["Quiet Trend", "Strong Trend", "Quiet Range", "Volatile Range"]:
        stats = summarize_regime(merged[merged["regime"] == regime])
        stats["regime"] = regime
        rows.append(stats)
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "regime_summary.csv", index=False)

    print(f"n_trades={len(merged)}")
    for r in rows:
        print(
            f"{r['regime']:14s} n={r['trades']:5d} wr={r['win_rate']:.4f} "
            f"pf={r['profit_factor']:.4f} avg_r={r['avg_r']:.4f} "
            f"exp=${r['expectancy_usd']:.2f} mae_r={r['avg_mae_r']:.3f} "
            f"mfe_r={r['avg_mfe_r']:.3f} loss_$={r['loss_dollars']:.0f} "
            f"adx={r['avg_adx']:.1f} atr_pct={r['avg_atr_pct']:.2f} "
            f"ema_slope={r['avg_ema50_slope_atr']:.3f}"
        )
    most_losses = max(rows, key=lambda r: r["loss_dollars"])
    print(f"regime with most loss $: {most_losses['regime']}")
    print(f"saved -> {RESULTS_DIR / 'regime_summary.csv'}")


if __name__ == "__main__":
    main()
