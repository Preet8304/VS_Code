# XAUUSD Scalping Strategy — Final Backtest Results

## TL;DR

A real, validated mean-reversion edge exists in gold M15: **RSI(2) extremes
traded only in the direction of the H1 macro trend**, exited at the first
profitable close (see `EDGE_ANALYSIS.md` for how this was found and what was
ruled out first). At a tight/ECN-grade spread it delivers the combination
originally asked for — **win rate ≈65-67%, profit factor ≈1.06-1.07,
positive return in both the in-sample and out-of-sample windows, and 7 of 11
calendar years profitable**. The catch, stated plainly: this is a thin edge
that is **net unprofitable at a standard retail fixed spread** ($0.35/oz). It
only works at execution costs around $0.10/oz round-turn — a raw/ECN account
with low commission, not a typical retail MT4/MT5 spread account.

## Data

- Source: `ejtraderLabs/historical-data` (public GitHub repo), fetched via
  `fetch_data.py`. XAUUSD M15 and H1 OHLC, 2012-05-15 → 2022-03-04
  (~230k M15 bars / ~58k H1 bars).
- Prices are vendor-scaled ×100 in the raw CSV (e.g. `196974` = $1,969.74);
  `data_loader.py` rescales to real USD/oz.
- Timestamps are the vendor's platform/broker time (commonly UTC+2/UTC+3),
  not strict UTC — the session-hour filter is tuned against this platform
  time.
- In-sample window: 2012-05-15 → 2018-12-31 (used for strategy design).
- Out-of-sample window: 2019-01-01 → 2022-03-04 (touched only once, after the
  design was locked, to validate honestly — see `EDGE_ANALYSIS.md` §3a for
  the raw-edge check on this exact split).

## Strategy logic (`strategy.py`, `backtest.py`)

Decision on each closed M15 bar, executed at the next bar's open (no
lookahead):

1. **Macro trend filter**: H1 EMA50 vs EMA200. Only buy oversold dips in an
   H1 uptrend, only sell overbought rallies in an H1 downtrend.
2. **Extreme trigger**: RSI(2) < 10 (long) or RSI(2) > 90 (short). This is
   the only entry trigger found to have a real, cost-independent raw edge —
   see `EDGE_ANALYSIS.md`.
3. **Volatility filter**: ATR percentile rank (100-bar lookback) between the
   20th and 90th percentile, to skip dead and abnormal-volatility regimes.
4. **Session filter**: 07:00–16:00 platform time (London/NY overlap).
5. **Exit**: protective stop at 1.5×ATR; otherwise exit at the close of the
   first bar after entry that closes in profit (`first_green` mode); a
   12-bar time-stop as a backstop if price never closes green.
6. **Sizing**: fixed-fractional risk, **0.25% of equity per trade** (see
   "Risk-per-trade and drawdown" below for why this was chosen over the
   initially-tried 0.5%).

## Backtest results (locked parameters, no further tuning)

Engine: signals at bar close, fills at next bar's open, half-spread paid on
each side of every trade, extra slippage on stop/time-stop market exits,
conservative same-bar SL resolution (assumes SL hit before TP/green-close if
both are touched in one bar), 0.25% fixed-fractional risk per trade, $10,000
starting equity.

| Scenario | Spread | Trades | Win rate | Profit factor | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| In-sample (2012–2018) | $0.35 (retail) | 3,140 | 57.6% | 0.74 | **−56.1%** | −57.5% | −2.15 |
| In-sample (2012–2018) | $0.10 (tight ECN) | 3,129 | 67.2% | 1.07 | **+20.6%** | −11.9% | 0.54 |
| Out-of-sample (2019–2022) | $0.35 (retail) | 1,631 | 59.2% | 0.76 | **−29.9%** | −30.2% | −1.75 |
| Out-of-sample (2019–2022) | $0.10 (tight ECN) | 1,621 | 66.2% | 1.06 | **+8.2%** | −7.8% | 0.43 |
| Full period (2012–2022) | $0.35 (retail) | 4,775 | 58.1% | 0.75 | **−69.5%** | −70.4% | −2.02 |
| Full period (2012–2022) | $0.10 (tight ECN) | 4,754 | 66.8% | 1.07 | **+29.8%** | −15.9% | 0.49 |

The win rate itself is *higher* at the tighter spread (67% vs 58%), not just
the P&L — because the `first_green` exit condition is "close back above
entry price," and a wider spread pushes the effective entry price further
away, making it structurally harder for price to close back above it before
the stop is hit instead. Spread does not just add a flat cost here; it
actively degrades the exit mechanic's hit rate.

### Yearly breakdown — full period, tight-ECN spread ($0.10), the only viable scenario

| Year | Trades | Win rate | P&L | Return |
|---|---|---|---|---|
| 2012 | 327 | 72.8% | +$1,166.07 | +11.7% |
| 2013 | 484 | 66.3% | −$113.86 | −1.0% |
| 2014 | 484 | 65.7% | +$195.95 | +1.8% |
| 2015 | 456 | 68.9% | +$1,145.06 | +10.2% |
| 2016 | 449 | 68.2% | +$160.28 | +1.3% |
| 2017 | 399 | 67.9% | +$589.84 | +4.7% |
| 2018 | 531 | 63.1% | −$1,083.66 | −8.2% |
| 2019 | 547 | 61.6% | −$748.51 | −6.2% |
| 2020 | 455 | 71.2% | +$611.53 | +5.4% |
| 2021 | 537 | 66.5% | +$1,240.81 | +10.4% |
| 2022* | 85 | 65.9% | −$182.68 | −1.4% |

*2022 partial (through March). 7 of 11 years are net positive; win rate is
above 60% in every single year, including the losing ones — the losing years
come from a higher average loss size on the stopped-out 33-40% of trades, not
from the win rate collapsing.

## Risk-per-trade and drawdown

Profit factor and win rate are **risk-size-invariant** — they depend only on
the entry/exit logic, not on position size. Drawdown, however, scales
roughly linearly with risk-per-trade. The first version of this system used
0.5% risk per trade, which produced the same 65-67% win rate and ~1.07 PF but
with a **−22% (IS) to −28% (full period) drawdown** — too large to be
comfortable running unattended. Halving risk to **0.25%** (the default now
baked into `backtest.py`'s `RiskModel` and `run_backtest.py`'s CLI default)
roughly halves the drawdown to −12-16% while leaving PF/win-rate exactly
where they were, since sizing doesn't touch signal quality. This is the
setting used for every result in this document and the one recommended for
any live/automated use.

## Cost (spread) sensitivity — full period, locked parameters

| Round-turn spread | Profit factor | Return (full period) |
|---|---|---|
| $0.00 | — | (see `EDGE_ANALYSIS.md` for the raw-signal-only breakeven, ≈$0.09-0.10) |
| $0.10 (tight ECN) | 1.07 | +29.8% |
| $0.35 (typical retail fixed spread) | 0.75 | −69.5% |

The system-level breakeven (including the `first_green` exit, not just the
raw entry signal) sits roughly between $0.10 and $0.17/oz round-turn.
Standard retail XAUUSD spreads are commonly $0.30–0.45/oz — this strategy
needs a genuine ECN/raw account with spread + commission under that
threshold to have any realistic chance of being profitable.

## Honest conclusion

The original ask was: find a real edge, get win rate near 65%, be
consistently profitable, and make it automation-ready. All four were
addressed directly rather than assumed:

1. **Real edge**: confirmed via null-baseline and raw (zero-cost) expectancy
   testing — see `EDGE_ANALYSIS.md`. RSI(2)-in-trend mean reversion is real;
   momentum/breakout is not.
2. **~65% win rate**: achieved (66.8% over the full period at viable cost),
   and unlike a naively-tuned system, this win rate is a side effect of a
   deliberately chosen exit rule on top of a real signal, not a geometry
   trick on a fake one (the null baseline in §1 of `EDGE_ANALYSIS.md` hits
   69% win rate with negative expectancy, which is exactly the failure mode
   being guarded against here).
3. **Consistent profitability**: 7 of 11 years profitable, win rate above
   60% in every single year — reasonably consistent, though not every year
   is a win, and the full-period drawdown is still −15.9% even at 0.25% risk.
4. **Automation readiness**: the strategy is mechanical and lookahead-free,
   which is necessary but not sufficient. The blocking constraint for live
   automation is **execution cost** — this needs to run on a broker/account
   with round-turn cost (spread + commission) under roughly $0.15-0.17/oz, or
   it will lose money exactly as the retail-spread rows above show. That is
   the one precondition to satisfy before automating this for live trading.

## Reproducing these results

```bash
cd xauusd_scalping
python3 fetch_data.py                       # downloads real data into data/
python3 research.py                         # edge discovery / what's real vs not (EDGE_ANALYSIS.md)

python3 run_backtest.py --start 2012-05-15 --end 2018-12-31 \
    --label is_retail --spread 0.35 --slippage 0.05
python3 run_backtest.py --start 2012-05-15 --end 2018-12-31 \
    --label is_ecn    --spread 0.10 --slippage 0.03
python3 run_backtest.py --start 2019-01-01 --end 2022-03-04 \
    --label oos_retail --spread 0.35 --slippage 0.05
python3 run_backtest.py --start 2019-01-01 --end 2022-03-04 \
    --label oos_ecn    --spread 0.10 --slippage 0.03
python3 run_backtest.py --start 2012-05-15 --end 2022-03-04 \
    --label full_retail --spread 0.35 --slippage 0.05
python3 run_backtest.py --start 2012-05-15 --end 2022-03-04 \
    --label full_ecn    --spread 0.10 --slippage 0.03
```

Trade logs, yearly breakdowns, and equity-curve plots are written to
`results/`.
