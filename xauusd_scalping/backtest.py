"""Bar-by-bar backtest engine with realistic cost/fill assumptions.

Fill model:
  - Signals are evaluated on the close of bar i; the trade is filled at the
    OPEN of bar i+1 (no lookahead).
  - Spread is modeled as half-spread paid on entry and half-spread paid on
    exit (a full round-turn spread per trade), applied as a price offset.
  - If both the stop-loss and take-profit fall inside the same bar's
    high/low range, the stop-loss is assumed to be hit first (conservative,
    since intrabar path is unknown from OHLC bars alone).
  - A small extra slippage is applied to stop-loss / time-stop exits since
    those are market-order exits in a fast-moving market; take-profit exits
    are treated as resting limit orders filled at the exact price.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from strategy import StrategyParams


@dataclass
class CostModel:
    spread: float = 0.35  # USD per oz, round turn
    stop_slippage: float = 0.05  # USD per oz, applied only on SL/time-stop exits


@dataclass
class RiskModel:
    initial_equity: float = 10_000.0
    risk_per_trade: float = 0.005  # fraction of current equity risked per trade


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit: float
    size_oz: float
    pnl: float
    r_multiple: float
    exit_reason: str
    bars_held: int


def _initial_stop_tp(
    direction: str, entry_price: float, atr_value: float, sma_value: float, params: StrategyParams
):
    """Stop is a fixed ATR multiple; target is mean reversion back to the
    SMA (Bollinger mid-band), floored at a minimum ATR distance so a trade
    entered right next to the band isn't given an unrealistically tiny
    target."""
    min_dist = params.tp_min_atr_mult * atr_value
    if direction == "long":
        stop = entry_price - params.sl_atr_mult * atr_value
        tp = max(sma_value, entry_price + min_dist)
    else:
        stop = entry_price + params.sl_atr_mult * atr_value
        tp = min(sma_value, entry_price - min_dist)
    return stop, tp


def run_backtest(
    df: pd.DataFrame,
    params: StrategyParams,
    costs: CostModel = CostModel(),
    risk: RiskModel = RiskModel(),
) -> tuple[list[Trade], pd.DataFrame]:
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
    equity_curve = np.empty(len(df))
    trades: list[Trade] = []

    pos = None  # dict holding open position state
    pending = None  # "long" / "short" queued to open at next bar's open

    n = len(df)
    for i in range(n):
        equity_curve[i] = equity

        if pos is not None:
            direction = pos["direction"]
            r_dist = abs(pos["entry_price"] - pos["stop_price"])

            if direction == "long":
                favorable = highs[i] - pos["entry_price"]
                if (
                    params.use_breakeven
                    and not pos["breakeven_done"]
                    and r_dist > 0
                    and favorable >= params.breakeven_at_r * r_dist
                ):
                    pos["stop_price"] = max(pos["stop_price"], pos["entry_price"])
                    pos["breakeven_done"] = True
                hit_sl = lows[i] <= pos["stop_price"]
                hit_tp = highs[i] >= pos["take_profit"]
            else:
                favorable = pos["entry_price"] - lows[i]
                if (
                    params.use_breakeven
                    and not pos["breakeven_done"]
                    and r_dist > 0
                    and favorable >= params.breakeven_at_r * r_dist
                ):
                    pos["stop_price"] = min(pos["stop_price"], pos["entry_price"])
                    pos["breakeven_done"] = True
                hit_sl = highs[i] >= pos["stop_price"]
                hit_tp = lows[i] <= pos["take_profit"]

            bars_held = i - pos["entry_index"]
            time_stop = bars_held >= params.max_holding_bars

            exit_reason = None
            exit_price = None
            if hit_sl:
                exit_reason = "stop_loss"
                raw_exit = pos["stop_price"]
                exit_price = raw_exit - costs.stop_slippage if direction == "long" else raw_exit + costs.stop_slippage
            elif hit_tp:
                exit_reason = "take_profit"
                exit_price = pos["take_profit"]
            elif time_stop:
                exit_reason = "time_stop"
                raw_exit = closes[i]
                exit_price = raw_exit - costs.stop_slippage if direction == "long" else raw_exit + costs.stop_slippage

            if exit_reason is not None:
                fill = exit_price - costs.spread / 2 if direction == "long" else exit_price + costs.spread / 2
                pnl = (fill - pos["entry_price"]) * pos["size_oz"] if direction == "long" else (pos["entry_price"] - fill) * pos["size_oz"]
                equity += pnl
                r_multiple = pnl / pos["risk_dollars"] if pos["risk_dollars"] else 0.0
                trades.append(
                    Trade(
                        entry_time=pos["entry_time"],
                        exit_time=times[i],
                        direction=direction,
                        entry_price=pos["entry_price"],
                        exit_price=fill,
                        stop_price=pos["stop_price"],
                        take_profit=pos["take_profit"],
                        size_oz=pos["size_oz"],
                        pnl=pnl,
                        r_multiple=r_multiple,
                        exit_reason=exit_reason,
                        bars_held=bars_held,
                    )
                )
                equity_curve[i] = equity
                pos = None

        if pending is not None and pos is None:
            direction = pending
            entry_price = opens[i] + costs.spread / 2 if direction == "long" else opens[i] - costs.spread / 2
            atr_value = atrs[i - 1] if i > 0 else atrs[i]
            sma_value = smas[i - 1] if i > 0 else smas[i]
            stop_price, take_profit = _initial_stop_tp(direction, entry_price, atr_value, sma_value, params)
            stop_dist = abs(entry_price - stop_price)
            risk_dollars = equity * risk.risk_per_trade
            size_oz = risk_dollars / stop_dist if stop_dist > 0 else 0.0
            pos = {
                "direction": direction,
                "entry_time": times[i],
                "entry_index": i,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "take_profit": take_profit,
                "size_oz": size_oz,
                "risk_dollars": risk_dollars,
                "breakeven_done": False,
            }
            pending = None

        if pos is None and pending is None:
            if long_sig[i]:
                pending = "long"
            elif short_sig[i]:
                pending = "short"

    df_out = df.copy()
    df_out["equity"] = equity_curve
    return trades, df_out
