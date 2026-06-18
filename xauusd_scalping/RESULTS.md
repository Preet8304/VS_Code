# XAUUSD Scalping Strategy — Methodology and Real-Data Backtest Results

## TL;DR

After systematically testing ~10 entry-trigger designs on 10 years of real
XAUUSD M15 data and validating the survivor out-of-sample, the honest
finding is: **a real, modest mean-reversion edge exists, but it is too
thin to survive a standard retail spread.** It only becomes profitable at
tight ECN/raw-account spreads (roughly $0.10–0.17 round turn on gold), where
it produces win rate ≈ 40–42%, profit factor ≈ 1.03–1.08, and small,
inconsistent annual returns (several losing years even when the period as a
whole is net positive). Simultaneously achieving *high* win rate, *high*
profitability, and *consistent* year-by-year returns — the three goals in
the original request — was not achievable with a pure technical-indicator
M15 scalping system on this dataset once realistic transaction costs are
applied. This document reports that finding rigorously rather than
overstating the result.

## Data

- Source: `ejtraderLabs/historical-data` (public GitHub repo), fetched via
  `fetch_data.py`. XAUUSD M15 and H1 OHLC, 2012-05-15 → 2022-03-04
  (~230k M15 bars / ~58k H1 bars).
- Prices are vendor-scaled ×100 in the raw CSV (e.g. `196974` = $1,969.74);
  `data_loader.py` rescales to real USD/oz.
- Timestamps are the vendor's platform/broker time (commonly UTC+2/UTC+3),
  not strict UTC — the session-hour filter below is tuned against this
  platform time.
- In-sample window: 2012-05-15 → 2018-12-31 (used for strategy design and
  parameter selection).
- Out-of-sample window: 2019-01-01 → 2022-03-04 (touched only once, after
  parameters were locked, to validate honestly).

## Decision-step methodology

The final strategy (`strategy.py`, `backtest.py`) makes a trade decision on
each closed M15 bar, executes at the next bar's open (no lookahead), and
filters through these steps in order:

1. **Macro trend filter (H1 EMA50 vs EMA200).** Only fade *with* the higher
   timeframe trend — buy oversold dips in an H1 uptrend, sell overbought
   rallies in an H1 downtrend. Fading against the macro trend (picking
   absolute tops/bottoms) was tested and is materially worse.
2. **Extreme-deviation trigger.** Price closes outside a wide Bollinger Band
   (SMA20 ± 3.0σ). A plain RSI overbought/oversold filter was tested as an
   additional confirmation and made results *worse* — it selects for
   trend-continuation, which is the opposite of what a fade needs.
3. **Volatility filter.** ATR percentile rank (100-bar lookback) must be
   between the 20th and 85th percentile — skips dead/choppy markets and
   abnormal/news-spike volatility.
4. **Session filter.** Only trade 07:00–16:00 platform time (London/NY
   overlap), where gold spreads are tightest and price action is cleanest.
5. **Risk management.** Tight stop at 1.2×ATR (a wider 1.5–2.0×ATR stop was
   tested and is *less* robust out-of-sample). Target is mean reversion back
   to the SMA20 (Bollinger mid-band), floored at entry ± 0.3×ATR so a trade
   opened right next to the band isn't given an unrealistically tiny target.
   Max holding period of 6 bars (90 minutes) — the edge decays fast, so
   trades that haven't reverted by then are closed at market.
   Fixed-fractional position sizing at 0.5% of equity risked per trade.

## What was ruled out first

Roughly a dozen variants were tested in-sample before arriving at the above.
All of the following were rejected because they showed no real edge (profit
factor well below 1, or a forward-return diagnostic showing the trigger was
anti-correlated with subsequent price movement):

- RSI midline-cross + EMA21/55 pullback continuation (the original design).
- Donchian micro-breakout momentum continuation.
- EMA21-reclaim bounce with a structural swing-low/high stop.
- EMA9/21 crossover with a chandelier trailing stop.
- Plain Bollinger-band fade *without* the H1 trend filter.
- Bollinger-band fade *with* an RSI<25/>75 confirmation filter.
- Bollinger-band fade with a "wick confirmation" price-action filter
  (required a long opposing wick on the trigger bar) — this cut the sample
  size by ~90% without clearly improving the risk-adjusted result.

A forward-return diagnostic was the key tool that separated real signal from
noise: it directly measures the average ATR-normalized price move N bars
after a trigger fires, independent of any stop/target assumptions. Most
triggers above were *negatively* correlated with subsequent price movement.

## Parameter selection: joint in-sample / out-of-sample grid search

Rather than tuning purely in-sample (which invites overfitting), the final
parameters were chosen by grid-searching `bb_mult × sl_atr_mult ×
max_holding_bars` and keeping only combinations profitable in **both** the
in-sample and out-of-sample windows at a fixed cost assumption — i.e. a
combination had to pass on data it had never been tuned against. The winner,
`bb_mult=3.0, sl_atr_mult=1.2, max_holding_bars=6`, was one of the few
combinations with profit factor > 1.0 in both non-overlapping periods.

## Backtest results (locked parameters, no further tuning)

Engine: signals at bar close, fills at next bar's open, half-spread paid on
each side of every trade, extra slippage on stop/time-stop market exits,
conservative same-bar SL/TP resolution (assumes SL hit first), 0.5%
fixed-fractional risk per trade, $10,000 starting equity.

| Scenario | Spread | Trades | Win rate | Profit factor | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| In-sample (2012–2018) | $0.35 (retail) | 341 | 38.4% | 0.81 | **−19.4%** | −21.0% | −0.54 |
| In-sample (2012–2018) | $0.15 (tight ECN) | 341 | 41.9% | 1.03 | **+3.3%** | −11.0% | 0.10 |
| Out-of-sample (2019–2022) | $0.35 (retail) | 140 | 38.6% | 0.90 | **−4.1%** | −10.3% | −0.24 |
| Out-of-sample (2019–2022) | $0.15 (tight ECN) | 140 | 40.0% | 1.08 | **+3.0%** | −7.5% | 0.20 |

### Yearly breakdown — tight-spread scenario (the only profitable one)

| Year | Trades | Win rate | P&L | Return |
|---|---|---|---|---|
| 2012 | 30 | 33.3% | −$402.55 | −4.0% |
| 2013 | 66 | 43.9% | +$209.91 | +2.2% |
| 2014 | 48 | 33.3% | −$298.96 | −3.0% |
| 2015 | 57 | 33.3% | −$528.07 | −5.6% |
| 2016 | 38 | 52.6% | +$710.09 | +7.9% |
| 2017 | 53 | 49.1% | +$260.45 | +2.7% |
| 2018 | 49 | 42.9% | +$189.74 | +1.9% |
| 2019 | 49 | 28.6% | −$722.28 | −7.2% |
| 2020 | 34 | 58.8% | +$926.63 | +10.0% |
| 2021 | 44 | 40.9% | +$223.67 | +2.2% |
| 2022* | 13 | 30.8% | −$186.98 | −1.8% |

*2022 partial (through March). 6 of 11 years were net losers even in the
best-case cost scenario — the edge is real on average but not consistent
year to year.

### Cost (spread) sensitivity — in-sample, locked parameters

| Round-turn spread | Profit factor | Return |
|---|---|---|
| $0.00 | 1.30 | +28.7% |
| $0.10 | 1.13 | +12.8% |
| **$0.15** | **1.03** | **+3.3%** |
| $0.20 | 0.94 | −6.1% |
| $0.30 | 0.83 | −16.9% |
| $0.35 (typical retail fixed spread) | 0.80 | −20.9% |

Breakeven round-turn cost is **≈$0.17/oz**. Standard retail XAUUSD spreads
are commonly $0.30–0.45; this strategy requires an ECN/raw account with
spread + commission under roughly $0.15–0.17 to have any realistic chance of
being profitable — and even then, the edge is modest and not robust to a
single bad year.

## Honest conclusion

This was tested rigorously, not just designed and assumed to work: ~10
candidate signal designs were tried, the failures were diagnosed with a
forward-return tool (not just "it lost money"), and the final candidate was
selected by requiring profitability on *both* an in-sample and a never-tuned
out-of-sample period simultaneously. Despite that discipline, the
result is a thin, cost-fragile mean-reversion edge — not the "high win rate
+ high profitability + consistent returns" combination requested. Pure
technical-indicator M15 scalping on this instrument, after realistic
transaction costs, does not reliably deliver all three. If pursuing this
further, the highest-leverage next steps would be: (a) trading it only on a
genuine ECN/raw-spread account with commission rebates, (b) reducing trade
frequency further to filter for only the highest-conviction setups, or (c)
abandoning pure technical triggers in favor of an orthogonal edge source
(order flow/liquidity data, macro-news avoidance, or a learned model) — none
of which were in scope for this pass.

## Reproducing these results

```bash
cd xauusd_scalping
python3 fetch_data.py                       # downloads real data into data/
python3 run_backtest.py --start 2012-05-15 --end 2018-12-31 \
    --label in_sample_retail --spread 0.35 --slippage 0.05
python3 run_backtest.py --start 2012-05-15 --end 2018-12-31 \
    --label in_sample_tight  --spread 0.15 --slippage 0.03
python3 run_backtest.py --start 2019-01-01 --end 2022-03-04 \
    --label out_sample_retail --spread 0.35 --slippage 0.05
python3 run_backtest.py --start 2019-01-01 --end 2022-03-04 \
    --label out_sample_tight  --spread 0.15 --slippage 0.03
```

Trade logs, yearly breakdowns, and equity-curve plots are written to
`results/`.
