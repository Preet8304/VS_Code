# XAUUSD Scalping Strategy — Final Backtest Results

## Correction notice (read this first)

A later review of the window/exit search behind the original version of this
document found a real selection-bias flaw: that search picked its winning
configuration by sorting candidates on `min(IS_PF, OOS_PF)`, which means the
nominally "out-of-sample" window was used **directly as a selection
criterion** across ~7,000 candidate configs, not just as an honest check
afterward. That is a form of data leakage — a multiple-comparisons bias —
even though it doesn't look like classic ML overfitting. It inflated the
headline numbers the original version reported (profit factor 1.53-1.60 for
a 14:00-16:00 session with a 0.5x/4.0x ATR exit).

This document has been rewritten end-to-end using a strict three-way split
that was never violated: **train** (2012-05-15 → 2016-12-31) to search,
**validate** (2017-01-01 → 2018-12-31) to shortlist, and **test**
(2019-01-01 → 2022-03-04) touched **exactly once**, with no further
adjustment after seeing the result. The corrected, locked configuration is
**session 13:00-16:00, stop 0.5×ATR, target 4.5×ATR (9:1 reward:risk)** —
close to the original but not identical, with honestly lower headline
numbers: full-period profit factor **1.41** (tight-ECN spread) / **1.10**
(retail spread), down from the previously claimed 1.53 / 1.13. See
"Correction: how the original search leaked, and the honest redo" below for
the full account, and `EDGE_ANALYSIS.md` §9 for the research-side detail.

The single most important new finding from this honest redo: **out-of-sample
performance at a standard retail spread is now negative** (profit factor
0.91, −18.3% return over 2019-2022), not "roughly breakeven" as the original
(leaky) version claimed. This strategy needs a genuinely tight, ECN-grade
spread to be reliably profitable — more so than previously stated, not less.

## TL;DR

A real, validated mean-reversion edge exists in gold M15: **RSI(2) extremes
traded only in the direction of the H1 macro trend** (see `EDGE_ANALYSIS.md`
for how this was found and what was ruled out first). On top of that signal,
narrowing the trading window to **13:00-16:00 (platform time)** and widening
the reward:risk ratio (0.5x ATR stop vs 4.5x ATR target, a 9:1 ratio) raises
full-period profit factor from the plain-session baseline of ~1.08-1.10 to
**1.41** at a tight-ECN spread (**1.10** at a standard retail spread), at the
cost of win rate dropping to **~19-21%** and trade count dropping to
**~150-200/year**. Both the window and the exit ratio were selected using
only the train+validate data (2012-2018); the 2019-2022 test window was
touched exactly once to confirm the choice, not to tune it — see the
correction section below for why that distinction matters and how it changed
the result.

## Data

- Source: `ejtraderLabs/historical-data` (public GitHub repo), fetched via
  `fetch_data.py`. XAUUSD M15 and H1 OHLC, 2012-05-15 → 2022-03-04
  (~230k M15 bars / ~58k H1 bars).
- Prices are vendor-scaled ×100 in the raw CSV (e.g. `196974` = $1,969.74);
  `data_loader.py` rescales to real USD/oz.
- Timestamps are the vendor's platform/broker time (commonly UTC+2/UTC+3),
  not strict UTC.
- Three-way split used for selecting the session window and exit ratio (see
  correction section below):
  - **Train**: 2012-05-15 → 2016-12-31 — searched exhaustively.
  - **Validate**: 2017-01-01 → 2018-12-31 — used to shortlist candidates that
    generalize, never to search.
  - **Test**: 2019-01-01 → 2022-03-04 — touched exactly once, after the
    config was already locked in.
- The standard backtest-results table further below also reports the
  simpler in-sample (2012-2018) / out-of-sample (2019-2022) split used
  elsewhere in this project, for consistency with `EDGE_ANALYSIS.md`.

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
4. **Session filter**: 13:00–16:00 platform time (see the correction section
   below for how this window was chosen honestly) — narrowed from the full
   07:00–16:00 session.
5. **Exit** (`exit_mode="atr_tp"`, the default): protective stop at 0.5×ATR;
   fixed target at 4.5×ATR (9:1 reward:risk). A 12-bar time-stop is a
   backstop for trades that hit neither. (`first_green` and the original
   1.0x/1.6x `atr_tp` geometry are still available in `strategy.py` for
   anyone who wants the higher win-rate / lower-PF tradeoff — see "Exit and
   session-window comparison" below.)
6. **Sizing**: fixed-fractional risk, **0.30% of equity per trade**, unchanged
   from the prior revision — full-period drawdown at this risk level turns
   out to be -13.9%, somewhat better than the -16% it was originally tuned
   against (see "Risk-per-trade and drawdown" below).

## Correction: how the original search leaked, and the honest redo

### What went wrong

The original version of this strategy widened reward:risk and then searched
for a better session window using an exhaustive scan of every
`(session_start_hour, session_end_hour)` pair. Candidates were ranked by
**`min(IS_PF, OOS_PF)`** — i.e. a config only ranked well if it scored well
on *both* the 2012-2018 in-sample window *and* the 2019-2022 out-of-sample
window. That sounds rigorous (it "confirms in both halves"), but it is not:
checking thousands of candidates against the OOS window and keeping the ones
that happen to score well there *is* using the OOS data to select the model,
just one level removed from classic train-on-test-data overfitting. The
out-of-sample window stopped being out-of-sample the moment it was used to
choose among candidates rather than to check a single, already-chosen one.

This was not caught before the original `RESULTS.md`/`EDGE_ANALYSIS.md` was
written. Re-running the same family of configs with a methodology that
cannot leak the same way shows the original headline figures (profit factor
1.53-1.60, 14:00-16:00 window, 0.5x/4.0x exit) were real but inflated, and
that the strategy's genuine out-of-sample-at-retail-spread performance is
materially worse than originally reported (negative, not "roughly
breakeven" — see below).

### The fix: a strict train → validate → test cascade

1. **Train** (2012-05-15 → 2016-12-31) only: an exhaustive grid over every
   `(session_start_hour, session_end_hour)` pair (275 windows with at least
   150 signals) crossed with stop multiples 0.5-1.0x and target multiples
   1.6-5.0x (filtered to reward:risk ≥ 1.5:1), for 13,152 valid candidate
   configs total. To make this tractable, `generate_signals()` was cached
   per session window and reused across all 48 stop/target combinations for
   that window, since signal generation doesn't depend on the exit
   parameters at all — this cut the number of (slow) signal-generation calls
   from ~13,000 to 275 and brought the full grid down to ~19 minutes.
2. **Anti-overfitting sample-size filter**: candidates were restricted to
   `train_n ≥ 500` before ranking (11,656 of the 13,152 candidates qualify).
   This deliberately excludes narrow 1-hour windows (e.g. 13:00-14:00,
   15:00-16:00) that top the raw train-profit-factor ranking on very few
   trades — exactly the kind of small-sample result most likely to be a
   curve-fit rather than a real effect.
3. **Shortlist by train, confirm by validate**: the top 15 surviving
   candidates by train profit factor were then evaluated, once each, against
   **validate** (2017-2018) — a window untouched by the train-only search.
   All 15 of 15 generalized with validate PF > 1.0 (range ≈1.23-1.53,
   train PF range ≈1.84-1.90). Random noise would not be expected to
   generalize this consistently across an independent, never-touched window
   — this is the strongest evidence in this redo that the underlying
   time-of-day effect is real, not an artifact of how the train grid was
   searched.
4. **Lock in by validate, before looking at test**: the single best
   candidate by validate profit factor — **session 13:00-16:00, stop
   0.5×ATR, target 4.5×ATR** — was selected and locked in. No other
   candidate was tried after this point.
5. **Touch test exactly once**: the locked candidate was then, and only
   then, evaluated against **test** (2019-2022), the window that had not
   been touched by any part of the search or shortlist process.

| Stage | Window | Trades | Win rate | Profit factor | Sharpe |
|---|---|---|---|---|---|
| Train (search) | 2012-05-15 → 2016-12-31 | 963 | 21.7% | **1.86** | 2.37 |
| Validate (shortlist) | 2017-01-01 → 2018-12-31 | 384 | 20.1% | **1.53** | 1.91 |
| Test (touched once) | 2019-01-01 → 2022-03-04 | 714 | 16.1% | **1.30** | 1.05 |

Profit factor declines monotonically from train to validate to test, which
is exactly the pattern an honest, non-leaky search should produce (some
fitting to train is unavoidable; what matters is that validate and test both
stay comfortably above 1.0, not that they match train). This table uses the
tight-ECN ($0.10/oz) spread throughout, since that is the cost level needed
for the underlying entry signal to be net-positive at all (see
`EDGE_ANALYSIS.md` §5); the standard results table further below reports
both ECN and retail spreads for in-sample/out-of-sample/full-period windows
in the format used elsewhere in this project (those numbers differ slightly
from the test row above — e.g. 713 vs. 714 trades — purely because of a
different end-date boundary convention between the two scripts; the two
estimates agree to within rounding).

### Sanity checks on the locked configuration (full period)

- **Not outlier-driven**: the 5 largest winning trades total $32,113 against
  $799,265 of gross profit — **4.0%** of the total. Profit factor is coming
  from the persistent shape of the win/loss distribution, not a handful of
  lucky trades.
- **Exit-reason mix is clean**: of 2,064 full-period trades, the overwhelming
  majority exit via `stop_loss` (1,662) or `take_profit` (271), with
  `time_stop` a small minority (131) — no sign of degenerate behavior from
  the wide target or narrow session.
- **Losing streaks are longer than the original (leaky) config implied**:
  the worst run in the full-period backtest is **32 consecutive losing
  trades** (up from 23 in the original, leaky-selected config). This is
  still statistically unsurprising at a ~19-21% win rate, but it is a real,
  slightly worse number that must be sized and planned for, and it is
  reported here precisely because the original document understated it.

## Exit and session-window comparison: the win-rate trade-off, made explicit

The entry signal is the only thing in this system with a demonstrated raw
edge (`EDGE_ANALYSIS.md`); everything downstream — win rate, profit factor,
return smoothness — is a function of the exit rule, the SL/TP ratio, and the
session window. Three configurations, all backtested end-to-end on the
identical entry signal at the tight-ECN spread ($0.10/oz) this edge needs to
clear cost at all:

| Config | Session | SL / TP (×ATR) | Win rate | Profit factor | Sharpe (IS / OOS) | Full-period return | Full-period DD | Profitable years |
|---|---|---|---|---|---|---|---|---|
| `first_green` | 07:00-16:00 | n/a (scratch exit) | 65-67% | 1.06-1.07 | 0.54 / 0.43 | +29.8%* | -15.9%* | 7 / 11 |
| `atr_tp` (original default) | 07:00-16:00 | 1.0 / 1.6 | 40-46% | 1.08-1.10 | 0.90 / 0.50 | +62.2%* | -16.3%* | 8 / 11 |
| `atr_tp` (**current default**) | 13:00-16:00 | 0.5 / 4.5 | 19-21% | 1.41 (full) | 2.23 / 1.01 | +2,303.2% | -13.9% | 11 / 11 |

*\*The first two rows are measured at their own previously-tuned
risk-per-trade (0.25% and 0.20% respectively); the current row is at 0.30%
risk/trade. Profit factor, win rate, and Sharpe are unaffected by
risk-per-trade; only return and drawdown scale with it. Unlike the prior
revision of this table, the current row's Sharpe column reports the simple
in-sample (2012-2018) / out-of-sample (2019-2022) split for comparability,
not the train/validate/test cascade from the correction section above.*

This is the trade actually made in this design: **win rate drops sharply
(40-46% → 19-21%) and trade frequency drops (~500/year → ~150-200/year) in
exchange for a meaningfully higher profit factor and Sharpe, and a much
larger compounded return at a comparable-or-lower drawdown.** A 9:1
reward:risk, ~20% win-rate system also means real losing streaks: the worst
run in the full-period backtest is **32 consecutive losing trades**, which
is statistically unsurprising at this win rate but must be expected and
sized for, not a sign of something broken. Anyone running this live needs to
be comfortable holding through stretches with no winning trade for an
extended period while the strategy waits for the next infrequent, large
winner to land.

If trade frequency or win-rate stability matters more than profit factor for
a given use case, the original 07:00-16:00 / 1.0x-1.6x design or the
`first_green` exit are still both fully supported via `StrategyParams`
overrides — nothing about the old design was removed, only the defaults
changed.

## Backtest results (locked parameters, no further tuning)

Engine: signals at bar close, fills at next bar's open, half-spread paid on
each side of every trade, extra slippage on stop/time-stop market exits,
conservative same-bar SL resolution, 0.30% fixed-fractional risk per trade,
$10,000 starting equity. `IS` = 2012-2018, `OOS` = 2019-2022 (the simple
two-way split used elsewhere in this project, not the train/validate/test
cascade above — see the correction section for why the cascade exists and
how it differs).

| Scenario | Spread | Trades | Win rate | Profit factor | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| In-sample (2012–2018) | $0.35 (retail) | 1,354 | 19.4% | 1.24 | **+236.4%** | −25.3% | 1.08 |
| In-sample (2012–2018) | $0.10 (tight ECN) | 1,347 | 21.2% | 1.65 | **+1,328.7%** | −13.9% | 2.23 |
| Out-of-sample (2019–2022) | $0.35 (retail) | 716 | 14.0% | **0.91** | **−18.3%** | −26.6% | −0.31 |
| Out-of-sample (2019–2022) | $0.10 (tight ECN) | 713 | 16.0% | 1.28 | **+70.0%** | −9.5% | 1.01 |
| Full period (2012–2022) | $0.35 (retail) | 2,073 | 17.5% | 1.10 | **+171.2%** | −43.7% | 0.63 |
| Full period (2012–2022) | $0.10 (tight ECN) | 2,063 | 19.4% | 1.41 | **+2,303.2%** | −13.9% | 1.84 |

**The headline downgrade from the original version of this document is the
out-of-sample-at-retail-spread row: profit factor 0.91, return −18.3%.** The
original (leaky-selected) config reported this as "roughly breakeven"
(PF 0.99, −0.9%); the honest redo shows it is actually a net loser at
standard retail cost. Out-of-sample at tight-ECN spread is still solidly
profitable (PF 1.28), and the full-period and in-sample numbers at both
spread levels remain clearly positive — but the retail-spread, out-of-sample
result is the soberest number in this document and should not be glossed
over: **this strategy is not yet shown to be tradable on a standard retail
spread looking forward; it needs genuinely tight, ECN-grade execution
cost.**

### Yearly breakdown — full period, tight-ECN spread ($0.10)

| Year | Trades | Win rate | P&L | Return |
|---|---|---|---|---|
| 2012 | 160 | 19.4% | +$3,337.29 | +33.4% |
| 2013 | 226 | 19.5% | +$4,819.89 | +36.1% |
| 2014 | 206 | 23.8% | +$11,609.97 | +63.9% |
| 2015 | 189 | 23.8% | +$20,427.25 | +68.6% |
| 2016 | 182 | 22.0% | +$23,756.10 | +47.3% |
| 2017 | 166 | 27.7% | +$67,657.01 | +91.5% |
| 2018 | 219 | 14.2% | +$774.14 | +0.6% |
| 2019 | 255 | 16.1% | +$10,604.06 | +7.5% |
| 2020 | 194 | 16.0% | +$30,257.66 | +19.8% |
| 2021 | 233 | 16.3% | +$54,495.19 | +29.7% |
| 2022* | 33 | 12.1% | +$2,582.31 | +1.1% |

*2022 partial (through March). **All 11 years are net positive** — an
improvement on the original document's "9 of 11" — but the distribution is
uneven: 2017 alone (+91.5%) and 2018 (+0.6%, barely positive) bookend a clear
soft patch, and a large share of the compounded full-period return comes
from a handful of standout years (2014-2017) rather than being spread evenly
across the backtest. Returns compound aggressively at 0.30% risk/trade over
a 10-year backtest (+2,303% cumulative) — this is a backtest artifact of
long-horizon compounding at fixed-fractional sizing, not a claim that this
rate is sustainable forever; see the cost-sensitivity and risk sections below
for the more load-bearing numbers (profit factor, Sharpe, drawdown).

## Risk-per-trade and drawdown

Profit factor and win rate are risk-size-invariant; only return and drawdown
scale with risk-per-trade. **0.30%** risk/trade was carried over unchanged
from the prior revision. At this setting, the current (corrected) config's
full-period drawdown is **−13.9%**, somewhat better than the −16.0% the
0.30% figure was originally chosen to match — a side benefit of the slightly
different locked parameters, not a re-tune performed this round.

## Cost (spread) sensitivity

| Round-turn spread | Profit factor (full period) | Return (full period) |
|---|---|---|
| $0.10 (tight ECN) | 1.41 | +2,303.2% |
| $0.35 (typical retail fixed spread) | 1.10 | +171.2% |

Full-period profit factor stays above 1.0 at both spread levels, so this
design remains, on net, not unconditionally unprofitable at a standard
retail spread when measured over the *entire* 2012-2022 backtest. But that
full-period number is carried disproportionately by the in-sample years —
**the out-of-sample window alone (2019-2022) is net negative at retail
spread** (PF 0.91, see the backtest-results table above), which the original
version of this document did not show. A genuine low-cost (ECN-grade)
account is not a "nice to have" for this strategy looking forward; based on
the honest out-of-sample evidence, it is closer to a requirement.

## Honest conclusion

1. **A real methodological flaw was found and fixed**: the original
   window/exit search selected its winning configuration by sorting on
   `min(IS_PF, OOS_PF)`, which used the out-of-sample window as a selection
   criterion across thousands of candidates rather than as a one-time check.
   This document has been rewritten using a leak-proof train → validate →
   test cascade (2012-16 → 2017-18 → 2019-22, test touched exactly once).
   See the correction section above for the full account.
2. **Real edge, confirmed**: via null-baseline and raw (zero-cost) expectancy
   testing — see `EDGE_ANALYSIS.md`. Unchanged by this correction; what
   changed is the honesty of how the harvesting parameters were chosen, not
   the underlying signal.
3. **Profit factor is real but lower than originally reported**: full-period
   **1.41 (ECN) / 1.10 (retail)**, train/validate/test cascade **1.86 / 1.53
   / 1.30**, all comfortably above 1.0 — but below the originally-claimed
   1.53-1.60. The honest number is the trustworthy one.
4. **A genuinely new, sobering finding**: out-of-sample performance at a
   standard retail spread is **negative** (PF 0.91, −18.3%), not "roughly
   breakeven" as originally claimed. This strategy's live-tradability at
   retail cost is weaker than the original document stated.
5. **The cost of the win-rate/frequency trade-off is also worse than
   originally stated**: win rate fell to ~19-21% and trade frequency to
   ~150-200/year (similar to before), but the worst losing streak in the
   full-period backtest is **32 consecutive losses**, up from the
   originally-reported 23 — a real, larger psychological and risk-sizing
   consideration for live trading.
6. **Consistent profitability remains, with a caveat**: 11 of 11 years
   net-positive at tight-ECN spread (up from 9 of 11), profit factor holds up
   from train through validate through test, and the sanity checks (4.0%
   top-5-wins share, clean exit-reason mix) still rule out "a few lucky
   trades" as the explanation — but a large share of the compounded return
   is concentrated in a handful of standout years (2014-2017), which any user
   of this strategy should weigh against the smoother, lower-PF designs still
   available (`first_green`, the original 1.0x/1.6x `atr_tp`).

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
fields to `StrategyParams` directly: `session_start_hour=14,
session_end_hour=16, sl_atr_mult=0.5, tp_atr_mult=4.0` reproduces the
original, leaky-selected config this document corrects (kept reproducible
for transparency, not recommended for use); `session_start_hour=7,
session_end_hour=16, sl_atr_mult=1.0, tp_atr_mult=1.6` reproduces the
original full-session design; `exit_mode="first_green"` reproduces the
original high-win-rate scratch exit (consider raising `risk_per_trade` back
to ~0.20-0.25% for either of those, since they have their own, smaller
drawdown budget at 0.30%).
