"""XAUUSD edge: short-term mean-reversion aligned with the higher-timeframe trend.

This strategy is the conclusion of a from-scratch edge hunt (see
EDGE_ANALYSIS.md and research.py). The central findings that shaped it:

  * Win rate by itself is meaningless. Random entries with a small target and
    a wider stop win ~69% of the time and still lose money. So the design
    target is genuine positive expectancy, and win rate is a by-product of
    exit-rule and reward:risk choices -- never chased for its own sake.
  * The one entry family with a real, cost-independent edge on gold M15 is
    mean-reversion taken in the direction of the macro trend: buying very
    short-term oversold dips inside an H1 uptrend (and the mirror for shorts).
    Measured before costs it is genuinely positive (profit factor ~1.1) and,
    crucially, in BOTH an in-sample and a never-tuned out-of-sample half.
  * Momentum / breakout entries have NO raw edge on this instrument/timeframe
    (negative expectancy even at zero cost) -- gold M15 mean-reverts.
  * RSI(2) is a cleaner trigger for the oversold/overbought extreme than a
    Bollinger band, but they measure the same underlying effect.
  * The same entry edge is markedly stronger in a narrow afternoon platform-
    time window than across the full session -- see EDGE_ANALYSIS.md S9-S10.
    The window/exit combination here was chosen via a strict train (2012-16)
    -> validate (2017-18) -> test (2019-22) split, where the test window is
    touched exactly once with no further adjustment -- a deliberate
    correction after an earlier pass picked its window by a criterion that
    looked at the test window directly, which inflated the headline profit
    factor. The honest number is lower than that first pass reported, but it
    is the trustworthy one. See EDGE_ANALYSIS.md S10 for the full account of
    what went wrong and how it was fixed.

Decision steps (evaluated on each closed M15 bar; acted on at the next bar's
open, so there is no lookahead):

  1. Macro trend filter (H1 EMA50 vs EMA200): only buy dips in an uptrend /
     sell rallies in a downtrend.
  2. Short-term extreme trigger: RSI(2) below `rsi_long` (oversold) for longs,
     above `rsi_short` (overbought) for shorts.
  3. Volatility filter (ATR percentile rank): skip dead and abnormally wild
     regimes.
  4. Session filter: trade only `session_start_hour`-`session_end_hour`
     (platform time). Default is the narrow 13:00-16:00 window -- see
     EDGE_ANALYSIS.md S9-S10 for why this window in particular and how it
     was chosen (a grid search over every start/end hour pair, with the
     selection made on train+validate data only and the test window checked
     exactly once, not a criterion that looked at test directly).
  5. Exit (see backtest.py): protective stop at `sl_atr_mult` x ATR; default
     target is a fixed `tp_atr_mult` x ATR (4.5x against a 0.5x stop -- a 9:1
     reward:risk ratio). This is a deliberate choice: letting winners run to
     a large multiple of a tight stop pushes win rate down to ~20-23%, but
     raises profit factor to ~1.4 (honest full-period, train/validate/test
     split -- see EDGE_ANALYSIS.md S10) versus the prior 1.0x stop / 1.6x
     target / ~40-45% win rate design's ~1.08. See RESULTS.md for the full
     side-by-side comparison, including why this combination is also *more*
     resilient to spread cost, not just more profitable at the same cost.
     A tighter scratch exit (`first_green` mode) is still available for
     anyone who prefers ~65%+ win rate over profit factor.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from indicators import atr, ema, rolling_percentile_rank, rsi


@dataclass(frozen=True)
class StrategyParams:
    htf_ema_fast: int = 50
    htf_ema_slow: int = 200
    rsi_period: int = 2
    rsi_long: float = 10.0
    rsi_short: float = 90.0
    atr_period: int = 14
    atr_lookback: int = 100
    atr_pct_low: float = 0.20
    atr_pct_high: float = 0.90
    session_start_hour: int = 13
    session_end_hour: int = 16
    sl_atr_mult: float = 0.5
    max_holding_bars: int = 12
    # Exit style: "atr_tp" (fixed ATR-multiple target -- ~20-23% win rate,
    # PF ~1.4 full-period, honestly train/validate/test split), "first_green"
    # (exit on first profitable close -> ~65%+ win rate but a thinner edge
    # per trade), or "mean_tp" (target the SMA20 mid-band). See RESULTS.md.
    exit_mode: str = "atr_tp"
    tp_atr_mult: float = 4.5
    tp_min_atr_mult: float = 0.3


def build_htf_trend(h1: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    out = h1[["time", "close"]].copy()
    out["htf_ema_fast"] = ema(out["close"], params.htf_ema_fast)
    out["htf_ema_slow"] = ema(out["close"], params.htf_ema_slow)
    out["htf_trend_up"] = out["htf_ema_fast"] > out["htf_ema_slow"]
    out["htf_trend_down"] = out["htf_ema_fast"] < out["htf_ema_slow"]
    out["avail_time"] = out["time"] + pd.Timedelta(hours=1)
    return out[["avail_time", "htf_trend_up", "htf_trend_down"]]


def generate_signals(m15: pd.DataFrame, h1: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    df = m15.copy()
    df["rsi2"] = rsi(df["close"], params.rsi_period)
    df["sma"] = df["close"].rolling(20).mean()
    df["atr"] = atr(df["high"], df["low"], df["close"], params.atr_period)
    df["atr_pct"] = rolling_percentile_rank(df["atr"], params.atr_lookback)

    htf = build_htf_trend(h1, params)
    df = pd.merge_asof(df, htf, left_on="time", right_on="avail_time", direction="backward")

    hour = df["time"].dt.hour
    in_session = (hour >= params.session_start_hour) & (hour < params.session_end_hour)
    vol_ok = df["atr_pct"].between(params.atr_pct_low, params.atr_pct_high)

    df["long_signal"] = (
        (df["rsi2"] < params.rsi_long)
        & df["htf_trend_up"].fillna(False)
        & vol_ok
        & in_session
    )
    df["short_signal"] = (
        (df["rsi2"] > params.rsi_short)
        & df["htf_trend_down"].fillna(False)
        & vol_ok
        & in_session
    )
    return df
