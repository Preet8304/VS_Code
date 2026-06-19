"""Edge-discovery harness for XAUUSD.

This is the tool used to decide what genuinely predicts gold and what does
not, rather than assuming an indicator works because it is popular. The core
idea is the TRIPLE-BARRIER test: from each candidate entry, walk forward over
the real intrabar high/low path and record which barrier (+target or -stop)
is touched first within a holding window. That yields the TRUE win rate and
expectancy of a given entry/target/stop geometry on real data.

Two facts this harness makes obvious (see EDGE_ANALYSIS.md):
  1. A high win rate is mostly a property of the target/stop geometry, not of
     edge: random entries with a small target and wider stop win ~69% of the
     time while still losing money. Win rate alone proves nothing.
  2. The only thing that matters is expectancy. Measuring it before AND after
     costs separates "is there a real edge?" from "does it survive the spread?"

Run directly to reproduce the edge survey:  python3 research.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_loader import load_h1, load_m15
from indicators import atr, ema, rolling_percentile_rank, rsi


def build_features(m15: pd.DataFrame, h1: pd.DataFrame) -> pd.DataFrame:
    """Attach every indicator the edge survey needs to the M15 frame, plus the
    H1 macro trend merged in without lookahead (a bar's trend is only available
    one hour after it opens, i.e. once it has closed)."""
    df = m15.copy()
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["sma20"] = df["close"].rolling(20).mean()
    df["std20"] = df["close"].rolling(20).std()
    df["rsi2"] = rsi(df["close"], 2)
    df["rsi14"] = rsi(df["close"], 14)
    df["atr"] = atr(df["high"], df["low"], df["close"], 14)
    df["atr_pct"] = rolling_percentile_rank(df["atr"], 100)
    df["hour"] = df["time"].dt.hour

    htf = h1[["time", "close"]].copy()
    htf["h_ef"] = ema(htf["close"], 50)
    htf["h_es"] = ema(htf["close"], 200)
    htf["up"] = htf["h_ef"] > htf["h_es"]
    htf["down"] = htf["h_ef"] < htf["h_es"]
    htf["avail"] = htf["time"] + pd.Timedelta(hours=1)
    df = pd.merge_asof(df, htf[["avail", "up", "down"]], left_on="time", right_on="avail", direction="backward")
    return df


def triple_barrier(
    df: pd.DataFrame,
    sig_long: pd.Series,
    sig_short: pd.Series,
    tp_atr: float | None,
    sl_atr: float,
    max_hold: int,
    spread: float = 0.35,
    slip: float = 0.05,
    tp_is_mean: bool = False,
) -> pd.DataFrame:
    """Evaluate signal QUALITY (every signal is a sample; no one-trade-at-a-time
    constraint). Entry at the next bar's open paying half-spread; exit at +target
    or -stop, whichever the real path hits first, else at the holding-window close.
    Conservative: if a single bar spans both barriers, count it as the stop."""
    o = df["open"].to_numpy(); h = df["high"].to_numpy(); l = df["low"].to_numpy(); c = df["close"].to_numpy()
    a = df["atr"].to_numpy(); mean = df["sma20"].to_numpy()
    n = len(df)
    out = []
    for idx_arr, direction in [(np.flatnonzero(sig_long.to_numpy()), 1), (np.flatnonzero(sig_short.to_numpy()), -1)]:
        for i in idx_arr:
            j = i + 1
            if j >= n:
                continue
            atr_v = a[i]
            if not np.isfinite(atr_v) or atr_v <= 0:
                continue
            entry = o[j] + direction * (spread / 2)
            if tp_is_mean:
                tp = mean[i]
                tp = max(tp, entry + 0.3 * atr_v) if direction == 1 else min(tp, entry - 0.3 * atr_v)
            else:
                tp = entry + direction * tp_atr * atr_v
            sl = entry - direction * sl_atr * atr_v
            win = None; exitp = None; bars = 0
            for k in range(j, min(j + max_hold, n)):
                bars = k - j
                hit_sl = (l[k] <= sl) if direction == 1 else (h[k] >= sl)
                hit_tp = (h[k] >= tp) if direction == 1 else (l[k] <= tp)
                if hit_sl:
                    exitp = sl - direction * slip; win = False; break
                if hit_tp:
                    exitp = tp; win = True; break
            if win is None:
                kk = min(j + max_hold, n) - 1
                exitp = c[kk] - direction * slip; bars = kk - j
                win = direction * (exitp - entry) > 0
            exitp = exitp - direction * (spread / 2)
            out.append((direction, win, direction * (exitp - entry), bars))
    return pd.DataFrame(out, columns=["dir", "win", "net_usd", "bars"])


def summarize_signal(r: pd.DataFrame) -> dict:
    if len(r) == 0:
        return {"n": 0}
    gp = r.loc[r.net_usd > 0, "net_usd"].sum()
    gl = -r.loc[r.net_usd <= 0, "net_usd"].sum()
    return {
        "n": len(r),
        "win": r["win"].mean(),
        "pf": gp / gl if gl > 0 else float("inf"),
        "avg_net": r["net_usd"].mean(),
    }


def _line(name: str, r: pd.DataFrame) -> None:
    s = summarize_signal(r)
    if s["n"] == 0:
        print(f"{name:40s} | no trades"); return
    print(f"{name:40s} | n={s['n']:5d} win={s['win']*100:5.1f}% PF={s['pf']:4.2f} avg_net={s['avg_net']:+6.3f}$/oz")


def main() -> None:
    df = build_features(load_m15(), load_h1())
    vol_ok = df["atr_pct"].between(0.2, 0.9)
    session = df["hour"].between(7, 15)
    up = df["up"].fillna(False); down = df["down"].fillna(False)
    empty = pd.Series(False, index=df.index)

    print("=" * 88)
    print("NULL BASELINE — random entries. Shows win rate is a geometry artifact, not edge.")
    print("=" * 88)
    rng = np.random.default_rng(42)
    rand = pd.Series(rng.random(len(df)) < 0.01) & vol_ok & session
    for tp, sl in [(1.0, 1.0), (0.5, 1.5)]:
        _line(f"random tp={tp} sl={sl}", triple_barrier(df, rand, empty, tp, sl, 16))

    print("=" * 88)
    print("THE EDGE — RSI(2) mean-reversion ALIGNED WITH H1 TREND, before vs after cost.")
    print("=" * 88)
    for thr in [5, 10]:
        sl_ = (df["rsi2"] < thr) & up & vol_ok & session
        ss_ = (df["rsi2"] > 100 - thr) & down & vol_ok & session
        _line(f"RSI2<{thr} trend  net@0.00", triple_barrier(df, sl_, ss_, 1.0, 1.5, 12, spread=0.0, slip=0.0))
        _line(f"RSI2<{thr} trend  net@0.10", triple_barrier(df, sl_, ss_, 1.0, 1.5, 12, spread=0.10, slip=0.02))
        _line(f"RSI2<{thr} trend  net@0.35", triple_barrier(df, sl_, ss_, 1.0, 1.5, 12, spread=0.35, slip=0.05))

    print("=" * 88)
    print("WHAT DOES NOT WORK — momentum/breakout has no raw edge in gold M15 (negative even at zero cost).")
    print("=" * 88)
    for N in [10, 20]:
        hh = df["high"].rolling(N).max().shift(1); ll = df["low"].rolling(N).min().shift(1)
        sl_ = (df["close"] > hh) & up & vol_ok & session
        ss_ = (df["close"] < ll) & down & vol_ok & session
        _line(f"{N}-bar breakout  net@0.00", triple_barrier(df, sl_, ss_, 2.0, 1.0, 24, spread=0.0, slip=0.0))


if __name__ == "__main__":
    main()
