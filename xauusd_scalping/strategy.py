"""XAUUSD trend-aligned Bollinger Band mean-reversion scalping strategy.

This is the strategy that survived rigorous testing on real M15 data. It is
the result of evaluating roughly a dozen entry-trigger archetypes (RSI
midline crosses, EMA pullbacks, Donchian breakouts, EMA crossovers with
trailing stops, plain Bollinger fades) and keeping only the one whose edge
held up out-of-sample, not just in-sample. See RESULTS.md for the full
comparison and an honest discussion of how thin/cost-sensitive this edge is.

Decision steps (evaluated on each closed M15 bar, signal acted on at the
next bar's open so there is no lookahead bias):

  1. Macro trend filter (H1): only fade *with* the higher timeframe trend
     (EMA50 vs EMA200), i.e. buy oversold dips in an H1 uptrend and sell
     overbought rallies in an H1 downtrend. Fading against the macro trend
     was tested and performs materially worse -- this is "buy the dip / sell
     the rally", not "pick the top/bottom".
  2. Extreme-deviation trigger: price closes outside a wide Bollinger Band
     (SMA20 +/- 3.0 std). Plain RSI-overbought/oversold confirmation was
     tested as an extra filter and made results worse (it selects for
     continuation, not exhaustion), so it is deliberately not used.
  3. Volatility filter (ATR percentile rank): skip dead/choppy markets and
     abnormally wild markets (news spikes, slippage risk).
  4. Session filter: only trade during London / NY liquidity hours.
  5. Risk management: tight ATR-based stop (1.2x ATR -- a wide stop was
     tested and is less robust out-of-sample), target is mean reversion back
     to the SMA20 (the Bollinger mid-band), floored at a minimum distance so
     a trade right next to the band isn't given an unrealistically small
     target. A short max holding period (6 bars / 90 minutes) cuts trades
     that don't revert quickly, since the edge decays fast.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from indicators import atr, ema, rolling_percentile_rank


@dataclass(frozen=True)
class StrategyParams:
    htf_ema_fast: int = 50
    htf_ema_slow: int = 200
    bb_period: int = 20
    bb_mult: float = 3.0
    atr_period: int = 14
    atr_lookback: int = 100
    atr_pct_low: float = 0.20
    atr_pct_high: float = 0.85
    session_start_hour: int = 7
    session_end_hour: int = 16
    sl_atr_mult: float = 1.2
    tp_min_atr_mult: float = 0.3
    max_holding_bars: int = 6
    use_breakeven: bool = False
    breakeven_at_r: float = 1.0


def build_htf_trend(h1: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    """Compute the H1 macro trend and timestamp when each bar's info is
    actually available to an M15 trader (one hour after the bar opens, i.e.
    once it has closed)."""
    out = h1[["time", "close"]].copy()
    out["htf_ema_fast"] = ema(out["close"], params.htf_ema_fast)
    out["htf_ema_slow"] = ema(out["close"], params.htf_ema_slow)
    out["htf_trend_up"] = out["htf_ema_fast"] > out["htf_ema_slow"]
    out["htf_trend_down"] = out["htf_ema_fast"] < out["htf_ema_slow"]
    out["avail_time"] = out["time"] + pd.Timedelta(hours=1)
    return out[["avail_time", "htf_trend_up", "htf_trend_down"]]


def generate_signals(m15: pd.DataFrame, h1: pd.DataFrame, params: StrategyParams) -> pd.DataFrame:
    df = m15.copy()
    df["sma"] = df["close"].rolling(params.bb_period).mean()
    df["std"] = df["close"].rolling(params.bb_period).std()
    df["bb_upper"] = df["sma"] + params.bb_mult * df["std"]
    df["bb_lower"] = df["sma"] - params.bb_mult * df["std"]
    df["atr"] = atr(df["high"], df["low"], df["close"], params.atr_period)
    df["atr_pct"] = rolling_percentile_rank(df["atr"], params.atr_lookback)

    htf = build_htf_trend(h1, params)
    df = pd.merge_asof(df, htf, left_on="time", right_on="avail_time", direction="backward")

    hour = df["time"].dt.hour
    in_session = (hour >= params.session_start_hour) & (hour < params.session_end_hour)
    vol_ok = df["atr_pct"].between(params.atr_pct_low, params.atr_pct_high)

    extreme_long = df["close"] < df["bb_lower"]
    extreme_short = df["close"] > df["bb_upper"]

    df["long_signal"] = (
        extreme_long
        & df["htf_trend_up"].fillna(False)
        & vol_ok
        & in_session
    )
    df["short_signal"] = (
        extreme_short
        & df["htf_trend_down"].fillna(False)
        & vol_ok
        & in_session
    )
    return df
