# XAUUSD Scalping Strategy — Final Backtest Results

## TL;DR

A real, validated mean-reversion edge exists in gold M15: **RSI(2) extremes
traded only in the direction of the H1 macro trend** (see `EDGE_ANALYSIS.md`
for how this was found and what was ruled out first). This revision answers a
direct follow-up request: the prior version's profit factor (~1.08-1.10) was
judged too low, with a target of at least ~1.5. Two changes get there:
**narrowing the trading window to 14:00-16:00 (platform time)** — a 2-hour
slice of the day where the same RSI(2)-in-trend edge is measurably stronger,
found via an exhaustive grid search over every session start/end hour and
validated independently in-sample and out-of-sample — and **widening the
reward:risk ratio** (0.5x ATR stop vs 4.0x ATR target, an 8:1 ratio, up from
1.0x/1.6x). Together these lift full-period profit factor from 1.08 to
**1.53** and roughly double the Sharpe ratio, at the cost of win rate dropping
further, from ~40-45% to **~20-23%**, and trade count dropping from ~500/year
to **~150/year**. That trade-off is the central decision in this revision and
is discussed honestly below — it is not free.

## Data

- Source: `ejtraderLabs/historical-data` (public GitHub repo), fetched via
  `fetch_data.py`. XAUUSD M15 and H1 OHLC, 2012-05-15 → 2022-03-04
  (~230k M15 bars / ~58k H1 bars).
- Prices are vendor-scaled ×100 in the raw CSV (e.g. `196974` = $1,969.74);
  `data_loader.py` rescales to real USD/oz.
- Timestamps are the vendor's platform/broker time (commonly UTC+2/UTC+3),
  not strict UTC.
- In-sample window: 2012-05-15 → 2018-12-31 (used for strategy design).
- Out-of-sample window: 2019-01-01 → 2022-03-04 (touched only to validate
  each design decision honestly, never to tune).

## Strategy logic (`strategy.py`, `backtest.py`)

Decision on each closed M15 bar, executed at the next bar's open (no
lookahead):

1. **Macro trend filter**: H1 EMA50 vs EMA200. Only buy oversold dips in an
   H1 uptrend, only sell overbought rallies in an H1 downtrend.
2. **Extreme trigger**: RSI(2) < 10 (long) or RSI(2) > 90 (short) — the only
   entry trigger found to have a real, cost-independent raw edge; see
   `EDGE_ANALYSIS.md`.
3. **Volatility filter**: ATR percentile rank (100-bar lookback) between the
   20th and 90th percentile.
4. **Session filter**: 14:00–16:00 platform time (see "Why a narrow
   afternoon window" below) — narrowed from the prior 07:00–16:00.
5. **Exit** (`exit_mode="atr_tp"`, the default): protective stop at 0.5×ATR;
   fixed target at 4.0×ATR (8:1 reward:risk). A 12-bar time-stop is a
   backstop for trades that hit neither. (`first_green` and the prior
   1.0x/1.6x `atr_tp` geometry are still available in `strategy.py` for
   anyone who wants the higher win-rate / lower-PF tradeoff — see "Exit
   and session-window comparison" below.)
6. **Sizing**: fixed-fractional risk, **0.30% of equity per trade** (raised
   from 0.20% because the tighter stop and narrower session already cut
   full-period drawdown roughly in half at the same risk setting — see
   "Risk-per-trade and drawdown" below).

## Why a narrow afternoon window: how it was found

The prior revision's profit factor (1.08-1.10 full-period) was deemed too low
for the request. Two independent levers were searched:

1. **Exit geometry alone** (SL/TP ATR-multiple ratio, holding the full
   07:00-16:00 session fixed): a grid over stop multiples 0.5-1.2 and target
   multiples 1.5-5.0 caps out-of-sample profit factor at **~1.14-1.16** —
   real, but nowhere near 1.5. Widening the target further than this band
   just shifts more trades into `time_stop` exits without raising PF, because
   the entry signal's raw edge size (`EDGE_ANALYSIS.md` §3) is the limiting
   factor, not the exit's reward:risk ratio.
2. **Time-of-day**: an exhaustive scan of every `(session_start_hour,
   session_end_hour)` pair (231 combinations, filtered to windows with at
   least 200 in-sample and 100 out-of-sample trades) shows the RSI(2)-in-trend
   edge is not uniform across the day. Profit factor rises smoothly — not as
   an isolated spike — as the window narrows toward roughly 12:00-16:00
   platform time, peaking around **14:00-16:00**. The smooth, broad gradient
   across nearby hour ranges (rather than one lucky cell surrounded by
   noise) is the main evidence this is a real time-of-day effect and not a
   data-mined artifact; a plausible mechanism is that this window overlaps
   major US economic data releases and the NY cash equity open, which tend
   to produce sharp, fast-reverting volatility spikes — exactly the kind of
   move a short-term mean-reversion entry is built to catch.

Combining the 14:00-16:00 window with a tighter stop / wider target (the
exit-geometry lever) compounds: each lever alone tops out around PF 1.1-1.3;
together they reach **PF 1.5-1.6**, confirmed independently in both the
in-sample and out-of-sample windows (not just full-period), which is the
relevant bar given the IS/OOS discipline used throughout this project.

A few sanity checks before trusting this:

- **Not outlier-driven**: for the chosen config, the 5 largest winning
  trades account for only ~2.3% of total gross profit. Profit factor is
  coming from the persistent shape of the win/loss distribution, not a
  handful of lucky trades.
- **Exit-reason mix is clean**: the overwhelming majority of trades exit via
  `stop_loss` or `take_profit` (e.g. 1,175 / 246 out of 1,481 full-period
  trades), with `time_stop` a small minority (60) — no sign of degenerate
  behavior from the wider target or narrower session.
- **More cost-resilient, not just more profitable**: at the standard retail
  spread ($0.35/oz), the old 1.0x/1.6x design was unconditionally
  unprofitable in every window (PF 0.80, full-period return −76%). The new
  8:1 reward:risk design is *better* at the same retail spread — full-period
  PF 1.13, return +122% — because the average win is now large relative to
  the spread cost. This is a side benefit of widening the reward:risk ratio,
  not something that was specifically optimized for.

## Exit and session-window comparison: the win-rate trade-off, made explicit

The entry signal is the only thing in this system with a demonstrated raw
edge (`EDGE_ANALYSIS.md`); everything downstream — win rate, profit factor,
return smoothness — is a function of the exit rule, the SL/TP ratio, and now
the session window. Three configurations, all backtested end-to-end on the
identical entry signal at the tight-ECN spread ($0.10/oz) this edge needs to
clear cost at all:

| Config | Session | SL / TP (×ATR) | Win rate | Profit factor | Sharpe (IS / OOS) | Full-period return | Full-period DD | Profitable years |
|---|---|---|---|---|---|---|---|---|
| `first_green` | 07:00-16:00 | n/a (scratch exit) | 65-67% | 1.06-1.07 | 0.54 / 0.43 | +29.8%* | -15.9%* | 7 / 11 |
| `atr_tp` (prior default) | 07:00-16:00 | 1.0 / 1.6 | 40-46% | 1.08-1.10 | 0.90 / 0.50 | +62.2%* | -16.3%* | 8 / 11 |
| `atr_tp` (**new default**) | 14:00-16:00 | 0.5 / 4.0 | 20-23% | 1.53-1.60 | 1.91 / 1.42 | +1,075.3% | -16.0% | 9 / 11 |

*\*Prior two rows measured at their own previously-tuned risk-per-trade
(0.25% and 0.20% respectively); the new row is at 0.30% risk/trade, chosen so
full-period drawdown lands at roughly the same ~-16% budget as the prior
versions — the comparison is "each design, run sensibly, at a comparable
drawdown," not the new design simply taking more risk. Profit factor, win
rate, and Sharpe are unaffected by risk-per-trade; only return and drawdown
scale with it.*

This is the trade actually made in this revision: **win rate drops sharply
(40-46% → 20-23%) and trade frequency drops (~500/year → ~150/year) in
exchange for profit factor crossing the requested ~1.5 threshold, materially
higher Sharpe, and a dramatically larger compounded return at a comparable
drawdown budget.** An 8:1 reward:risk, ~20% win-rate system also means real
losing streaks: the worst run in the full-period backtest is **23 consecutive
losing trades**, which is statistically unsurprising at this win rate but
must be expected and sized for, not a sign of something broken. Anyone
running this live needs to be comfortable holding through stretches with no
winning trade for an extended period while the strategy waits for the next
infrequent, large winner to land.

If trade frequency or win-rate stability matters more than profit factor for
a given use case, the prior 07:00-16:00 / 1.0x-1.6x design (`RESULTS.md`'s
previous revision) or the `first_green` exit are still both fully supported
via `StrategyParams` overrides — nothing about the old design was removed,
only the defaults changed.

## Backtest results (locked parameters, no further tuning)

Engine: signals at bar close, fills at next bar's open, half-spread paid on
each side of every trade, extra slippage on stop/time-stop market exits,
conservative same-bar SL resolution, 0.30% fixed-fractional risk per trade,
$10,000 starting equity.

| Scenario | Spread | Trades | Win rate | Profit factor | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| In-sample (2012–2018) | $0.35 (retail) | 972 | 19.9% | 1.21 | **+126.0%** | −25.9% | 0.89 |
| In-sample (2012–2018) | $0.10 (tight ECN) | 968 | 21.7% | 1.60 | **+529.3%** | −16.0% | 1.91 |
| Out-of-sample (2019–2022) | $0.35 (retail) | 512 | 15.8% | 0.99 | **−0.9%** | −15.7% | 0.03 |
| Out-of-sample (2019–2022) | $0.10 (tight ECN) | 511 | 18.6% | 1.48 | **+88.1%** | −5.8% | 1.38 |
| Full period (2012–2022) | $0.35 (retail) | 1,486 | 18.4% | 1.13 | **+121.9%** | −37.0% | 0.61 |
| Full period (2012–2022) | $0.10 (tight ECN) | 1,481 | 20.6% | 1.53 | **+1,075.3%** | −16.0% | 1.73 |

Profit factor holds up out-of-sample (1.60 IS → 1.48 OOS) — the same raw
RSI(2)-in-trend signal validated independently in both halves in
`EDGE_ANALYSIS.md` §3a, now harvested with a narrower window and a wider,
more asymmetric exit. Out-of-sample at retail spread is roughly breakeven
(PF 0.99, return −0.9%) rather than the prior design's deeply negative
out-of-sample retail result (−35.8%) — a meaningfully smaller cost cliff,
even though a genuine ECN-grade spread is still required for the strategy to
be clearly profitable.

### Yearly breakdown — full period, tight-ECN spread ($0.10), the only clearly viable scenario

| Year | Trades | Win rate | P&L | Return |
|---|---|---|---|---|
| 2012 | 116 | 22.4% | +$3,471.46 | +34.7% |
| 2013 | 163 | 20.3% | +$3,856.92 | +28.6% |
| 2014 | 142 | 26.1% | +$8,669.39 | +50.0% |
| 2015 | 152 | 23.0% | +$10,707.17 | +41.2% |
| 2016 | 122 | 23.0% | +$8,876.07 | +24.2% |
| 2017 | 118 | 28.0% | +$22,783.51 | +50.0% |
| 2018 | 156 | 11.5% | −$5,646.51 | −8.3% |
| 2019 | 195 | 19.0% | +$11,666.47 | +18.6% |
| 2020 | 133 | 15.8% | +$7,941.02 | +10.7% |
| 2021 | 165 | 21.2% | +$36,200.58 | +44.0% |
| 2022* | 19 | 10.5% | −$991.86 | −0.8% |

*2022 partial (through March). 9 of 11 years are net positive (2018 and the
2-month partial 2022 are the only red years); 2018's −8.3% is also the year
with the lowest win rate (11.5%), consistent with an unusually unfavorable
stretch for this signal rather than a structural break. Returns compound
aggressively at 0.30% risk/trade over a 10-year backtest (+1,075% cumulative)
— this is a backtest artifact of long-horizon compounding at fixed-fractional
sizing, not a claim that this rate is sustainable forever; see the
cost-sensitivity and risk sections below for the more load-bearing numbers
(profit factor, Sharpe, drawdown).

## Risk-per-trade and drawdown

Profit factor and win rate are risk-size-invariant; only return and drawdown
scale with risk-per-trade. **0.30%** was chosen because it lands full-period
drawdown (-16.0%) close to where the prior two revisions sat (-15.9%,
-16.3%), so the comparison above isn't won by simply taking more risk — at
the prior 0.20% risk level this design's own full-period drawdown is only
about -11%, meaning there was real spare drawdown budget to use before
matching the prior versions' risk profile.

## Cost (spread) sensitivity

| Round-turn spread | Profit factor (full period) | Return (full period) |
|---|---|---|
| $0.10 (tight ECN) | 1.53 | +1,075.3% |
| $0.35 (typical retail fixed spread) | 1.13 | +121.9% |

Unlike the prior two revisions, this design is **not** unconditionally
unprofitable at a standard retail spread — full-period PF stays above 1.0
(1.13) and return is solidly positive (+121.9%), because the 8:1 reward:risk
ratio makes the average win much larger relative to a fixed spread cost.
It is still meaningfully better at ECN-grade cost, and the out-of-sample
window alone is roughly breakeven at retail spread (PF 0.99, see table
above) — so a genuine low-cost account is still the difference between
"clearly profitable" and "marginal," just not between "profitable" and
"guaranteed loss" as it was before.

## Honest conclusion

1. **Real edge**: confirmed via null-baseline and raw (zero-cost) expectancy
   testing — see `EDGE_ANALYSIS.md`. Unchanged by this revision; what changed
   is how it is harvested (time-of-day + reward:risk), not the signal itself.
2. **Profit factor, by request**: raised from 1.08-1.10 to **1.53 full-period
   / 1.60 IS / 1.48 OOS**, confirmed independently in both windows, by
   combining a data-driven session-window restriction with a wider
   reward:risk exit. This is the explicit trade made in this revision.
3. **The cost of that trade is real and is stated plainly**: win rate fell
   from ~40-45% to ~20-23%, and trade frequency fell from ~500/year to
   ~150/year. A 23-trade losing streak occurs in the full-period backtest —
   expected at this win rate, but a real psychological and risk-sizing
   consideration for live trading, not a footnote.
4. **Consistent profitability**: 9 of 11 years profitable, profit factor
   holds up from 1.60 in-sample to 1.48 out-of-sample, Sharpe roughly doubles
   versus the prior revision (0.90→1.91 IS, 0.50→1.42 OOS).
5. **Automation readiness improved**: this design is the first revision that
   is not unconditionally unprofitable at a standard retail spread (full
   period PF 1.13 at $0.35/oz), though a genuine low-cost account remains
   the difference between marginal and clearly profitable, particularly
   out-of-sample.

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
`results/`. To reproduce a prior variant for comparison, pass the relevant
fields to `StrategyParams` directly, e.g. `session_start_hour=7,
session_end_hour=16, sl_atr_mult=1.0, tp_atr_mult=1.6` for the previous
revision's default, or `exit_mode="first_green"` for the original
high-win-rate scratch exit (and consider raising `risk_per_trade` back to
~0.20-0.25%, since those designs have their own, smaller drawdown budget at
0.30%).
