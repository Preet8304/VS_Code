"""Deep dive into one regime only: "Strong Trend" (ADX >= 25 and ATR-pct >=
0.5, i.e. "Strong Trend + High Volatility" in regime_analysis.py's 2x2 grid),
the regime flagged there as both the largest (659/2,064 trades) and weakest
(PF 1.22) of the four. This is regime RESEARCH, not optimization: every
number below describes the existing 659 trades exactly as audit.py already
computed them (no entry, sizing, or exit change of any kind here) -- this
script reads `results/trade_regime_full_ecn.csv`, the file regime_analysis.py
already produced and validated, and slices/bins it. The stop-management
simulation requested alongside this breakdown lives in the companion script
`strong_trend_stop_models.py` (it needs a bar-by-bar replay, not just a
slice of an existing CSV).

Run `python3 strong_trend_analysis.py` to reproduce every descriptive number
in STRONG_TREND_ANALYSIS.md.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def pf(group: pd.DataFrame) -> float:
    # R-multiple-based, not dollar-pnl-based -- see the methodology note in
    # STRONG_TREND_ANALYSIS.md. Dollar pnl in any slice that isn't the full
    # chronological sequence from the very first trade is generated off the
    # REAL, unevenly-compounded historical equity at each trade's own point
    # in time; summing it directly into a PF ratio mixes eras at different
    # equity scale and skews the result (confirmed directly: this exact
    # 659-trade Strong Trend slice gives PF=1.2152 by dollar pnl vs
    # PF=1.4018 by R-multiple -- the same bias session_analysis.py already
    # found and fixed for by-year drawdown, here showing up in PF instead).
    gp = group.loc[group["r_multiple"] > 0, "r_multiple"].sum()
    gl = -group.loc[group["r_multiple"] <= 0, "r_multiple"].sum()
    return gp / gl if gl > 0 else float("inf")


def win_rate(group: pd.DataFrame) -> float:
    n = len(group)
    return (group["pnl"] > 0).sum() / n if n else 0.0


def basic_stats(group: pd.DataFrame) -> dict:
    n = len(group)
    losses = group[group["pnl"] <= 0]
    return {
        "trades": n,
        "win_rate": win_rate(group),
        "profit_factor": pf(group),
        "avg_r": group["r_multiple"].mean() if n else 0.0,
        "expectancy_usd": group["pnl"].mean() if n else 0.0,
        "loss_count": len(losses),
        "loss_dollars": float(-losses["pnl"].sum()) if n else 0.0,
    }


def main() -> None:
    full = pd.read_csv(RESULTS_DIR / "trade_regime_full_ecn.csv", parse_dates=["entry_time", "exit_time"])
    st = full[full["regime"] == "Strong Trend"].copy()
    st["year"] = st["entry_time"].dt.year
    st["is_loss"] = st["pnl"] <= 0
    print(f"Strong Trend regime: n={len(st)} (of {len(full)} total trades)")

    cols = [
        "entry_time", "direction", "adx_sig", "atr_pct_sig", "ema50_slope_sig",
        "pnl", "r_multiple", "mfe_r", "mae_r", "bars_held", "exit_reason", "is_loss",
    ]
    st[cols].to_csv(RESULTS_DIR / "strong_trend_trades.csv", index=False)
    print(f"saved per-trade record -> {RESULTS_DIR / 'strong_trend_trades.csv'}")

    # --- Q1: do losses come from longs, shorts, or both? ---
    print("\n--- Q1: losses by direction ---")
    by_dir_rows = []
    for d in ["long", "short"]:
        g = st[st["direction"] == d]
        s = basic_stats(g)
        s["direction"] = d
        by_dir_rows.append(s)
        print(f"{d:6s} n={s['trades']:4d} wr={s['win_rate']:.4f} pf={s['profit_factor']:.4f} "
              f"avg_r={s['avg_r']:.4f} loss_n={s['loss_count']} loss_$={s['loss_dollars']:.0f}")
    pd.DataFrame(by_dir_rows).to_csv(RESULTS_DIR / "strong_trend_by_direction.csv", index=False)

    # --- Q2: are losses concentrated in specific years? ---
    print("\n--- Q2: by year ---")
    by_year_rows = []
    for yr, g in st.groupby("year"):
        s = basic_stats(g)
        s["year"] = yr
        by_year_rows.append(s)
        print(f"{yr} n={s['trades']:4d} wr={s['win_rate']:.4f} pf={s['profit_factor']:.4f} "
              f"avg_r={s['avg_r']:.4f} loss_n={s['loss_count']} loss_$={s['loss_dollars']:.0f}")
    by_year_df = pd.DataFrame(by_year_rows)
    by_year_df.to_csv(RESULTS_DIR / "strong_trend_by_year.csv", index=False)

    # --- Q3: do losers cluster at extremely high ATR percentiles? ---
    print("\n--- Q3: atr_pct_sig, losers vs winners ---")
    losers = st[st["is_loss"]]
    winners = st[~st["is_loss"]]
    for label, g in [("losers", losers), ("winners", winners)]:
        d = g["atr_pct_sig"].describe(percentiles=[0.5, 0.75, 0.9])
        print(f"{label}: mean={d['mean']:.3f} median={d['50%']:.3f} p75={d['75%']:.3f} "
              f"p90={d['90%']:.3f} max={d['max']:.3f}")

    # --- Q4: ATR-percentile bins, holding ADX trend-condition fixed ---
    # Universe: ADX >= 25 (both "Quiet Trend" and "Strong Trend" regime-grid
    # cells), i.e. the trend-condition half of the 2x2 grid, with the
    # volatility axis left free to range over its full span instead of being
    # cut at the grid's own 0.5 split. This is the natural complementary
    # slice to ask "where inside the trending population does volatility
    # start to hurt" -- holding the OTHER defining axis (ADX) fixed at the
    # regime's own condition, varying only the axis under test.
    print("\n--- Q4: ATR-percentile bins (ADX>=25 universe) ---")
    trend_universe = full[full["adx_sig"] >= 25].copy()
    print(f"(ADX>=25 universe: n={len(trend_universe)})")
    atr_bins = [(0.0, 0.70), (0.70, 0.85), (0.85, 0.95), (0.95, 1.0001)]
    atr_bin_rows = []
    for lo, hi in atr_bins:
        g = trend_universe[(trend_universe["atr_pct_sig"] >= lo) & (trend_universe["atr_pct_sig"] < hi)]
        s = basic_stats(g)
        label = f"{int(round(lo*100))}-{int(round(min(hi,1.0)*100))}"
        s["atr_pct_bin"] = label
        atr_bin_rows.append(s)
        print(f"atr_pct {label:7s} n={s['trades']:4d} wr={s['win_rate']:.4f} "
              f"pf={s['profit_factor']:.4f} exp=${s['expectancy_usd']:.2f} avg_r={s['avg_r']:.4f}")
    pd.DataFrame(atr_bin_rows).to_csv(RESULTS_DIR / "strong_trend_atr_bins.csv", index=False)

    # --- Q4b: same ATR-percentile bins, but purely *within* the 659-trade
    # Strong Trend bucket itself (which already requires atr_pct>=0.5) --
    # the most direct cut for "focus exclusively on Strong Trend": where
    # inside the regime under research does the cliff actually sit.
    print("\n--- Q4b: ATR-percentile bins, within Strong Trend itself (n=659) ---")
    st_atr_bins = [(0.5, 0.70), (0.70, 0.85), (0.85, 0.95), (0.95, 1.0001)]
    st_atr_bin_rows = []
    for lo, hi in st_atr_bins:
        g = st[(st["atr_pct_sig"] >= lo) & (st["atr_pct_sig"] < hi)]
        s = basic_stats(g)
        label = f"{int(round(lo*100))}-{int(round(min(hi,1.0)*100))}"
        s["atr_pct_bin"] = label
        st_atr_bin_rows.append(s)
        print(f"atr_pct {label:7s} n={s['trades']:4d} wr={s['win_rate']:.4f} "
              f"pf={s['profit_factor']:.4f} exp=${s['expectancy_usd']:.2f} avg_r={s['avg_r']:.4f}")
    pd.DataFrame(st_atr_bin_rows).to_csv(RESULTS_DIR / "strong_trend_atr_bins_within.csv", index=False)

    # --- Q5: ADX bins, holding the volatility condition fixed ---
    # Universe: atr_pct_sig >= 0.5 (both "Strong Trend" and "Volatile Range"
    # grid cells) -- the volatility-condition half of the grid, ADX left
    # free, mirroring Q4's design exactly but on the other axis.
    print("\n--- Q5: ADX bins (ATR-pct>=0.5 universe) ---")
    vol_universe = full[full["atr_pct_sig"] >= 0.5].copy()
    print(f"(ATR-pct>=0.5 universe: n={len(vol_universe)})")
    below_20 = vol_universe[vol_universe["adx_sig"] < 20]
    if len(below_20):
        s = basic_stats(below_20)
        print(f"adx_sig <20     n={s['trades']:4d} wr={s['win_rate']:.4f} pf={s['profit_factor']:.4f} "
              f"exp=${s['expectancy_usd']:.2f} avg_r={s['avg_r']:.4f}  (not a requested bin, shown for completeness)")
    adx_bins = [(20, 25), (25, 30), (30, 40), (40, 999)]
    adx_bin_rows = []
    for lo, hi in adx_bins:
        g = vol_universe[(vol_universe["adx_sig"] >= lo) & (vol_universe["adx_sig"] < hi)]
        s = basic_stats(g)
        label = f"{lo}-{hi}" if hi < 999 else f"{lo}+"
        s["adx_bin"] = label
        adx_bin_rows.append(s)
        print(f"adx_sig {label:7s} n={s['trades']:4d} wr={s['win_rate']:.4f} "
              f"pf={s['profit_factor']:.4f} exp=${s['expectancy_usd']:.2f} avg_r={s['avg_r']:.4f}")
    pd.DataFrame(adx_bin_rows).to_csv(RESULTS_DIR / "strong_trend_adx_bins.csv", index=False)

    # --- Q5b: same ADX bins, purely within the 659-trade Strong Trend
    # bucket itself (which already requires ADX>=25) ---
    print("\n--- Q5b: ADX bins, within Strong Trend itself (n=659) ---")
    st_adx_bins = [(25, 30), (30, 40), (40, 999)]
    st_adx_bin_rows = []
    for lo, hi in st_adx_bins:
        g = st[(st["adx_sig"] >= lo) & (st["adx_sig"] < hi)]
        s = basic_stats(g)
        label = f"{lo}-{hi}" if hi < 999 else f"{lo}+"
        s["adx_bin"] = label
        st_adx_bin_rows.append(s)
        print(f"adx_sig {label:7s} n={s['trades']:4d} wr={s['win_rate']:.4f} "
              f"pf={s['profit_factor']:.4f} exp=${s['expectancy_usd']:.2f} avg_r={s['avg_r']:.4f}")
    pd.DataFrame(st_adx_bin_rows).to_csv(RESULTS_DIR / "strong_trend_adx_bins_within.csv", index=False)

    # --- Losing trades held >=2 bars: MFE reached before eventual stopout ---
    print("\n--- Losers held >=2 bars: MFE-in-R before stopout ---")
    slow_losers = losers[losers["bars_held"] >= 2]
    print(f"n={len(slow_losers)} of {len(losers)} total losers ({len(slow_losers)/len(losers)*100:.1f}%)")
    d = slow_losers["mfe_r"].describe(percentiles=[0.5, 0.75, 0.9])
    print(f"mfe_r: mean={d['mean']:.3f} median={d['50%']:.3f} p75={d['75%']:.3f} "
          f"p90={d['90%']:.3f} max={d['max']:.3f}")
    print(f"share reaching >=1R MFE before stopping out: {(slow_losers['mfe_r'] >= 1.0).mean()*100:.1f}%")
    print(f"share reaching >=2R MFE before stopping out: {(slow_losers['mfe_r'] >= 2.0).mean()*100:.1f}%")
    slow_losers.to_csv(RESULTS_DIR / "strong_trend_slow_losers.csv", index=False)


if __name__ == "__main__":
    main()
