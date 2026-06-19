"""XAUUSD edge: short-term mean-reversion aligned with the higher-timeframe trend.

This strategy is the conclusion of a from-scratch edge hunt (see
EDGE_ANALYSIS.md and research.py). The central findings that shaped it:

  * Win rate by itself is meaningless. Random entries with a small target and
    a wider stop win ~69% of the time and still lose money. So the design
    target is genuine positive expectancy, and a high win rate is obtained
    only as a by-product of an exit rule -- never chased for its own sake.
  * The one entry family with a real, cost-independent edge on gold M15 is
    mean-reversion taken in the direction of the macro trend: buying very
    short-term oversold dips inside an H1 uptrend (and the mirror for shorts).
    Measured before costs it is genuinely positive (profit factor ~1.1) and,
    crucially, in BOTH an in-sample and a never-tuned out-of-sample half.
  * Momentum / breakout entries have NO raw edge on this instrument/timeframe
    (negative expectancy even at zero cost) -- gold M15 mean-reverts.
  * RSI(2) is a cleaner trigger for the oversold/overbought extreme than a
    Bollinger band, but they measure the same underlying effect.

Decision steps (evaluated on each closed M15 bar; acted on at the next bar's
open, so there is no lookahead):

  1. Macro trend filter (H1 EMA50 vs EMA200): only buy dips in an uptrend /
     sell rallies in a downtrend.
  2. Short-term extreme trigger: RSI(2) below `rsi_long` (oversold) for longs,
     above `rsi_short` (overbought) for shorts.
  3. Volatility filter (ATR percentile rank): skip dead and abnormally wild
     regimes.
  4. Session filter: trade only the liquid London/NY window.
  5. Exit (see backtest.py): protective stop at `sl_atr_mult` x ATR, and -- in
     the default `first_green` mode -- exit at the first bar that closes in
     profit. That scratch exit is what lifts the win rate to ~65%+, but the
     system is only net profitable on raw/ECN-grade spreads (the edge is real
     yet smaller than a typical retail gold spread; see EDGE_ANALYSIS.md).
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
    session_start_hour: int = 7
    session_end_hour: int = 16
    sl_atr_mult: float = 1.5
    max_holding_bars: int = 12
    # Exit style: "first_green" (exit on first profitable close -> high win rate),
    # "mean_tp" (target the SMA20 mid-band), or "atr_tp" (fixed ATR multiple).
    exit_mode: str = "first_green"
    tp_atr_mult: float = 1.0
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
