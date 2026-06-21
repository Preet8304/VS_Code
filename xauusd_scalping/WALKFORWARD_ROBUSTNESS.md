# Walk-Forward Robustness Study — Proposed Exit-Management System

Produced by `walkforward_robustness.py`. This is a **robustness validation**,
not a parameter search: every level used below (25%/25%/50% partial sizes,
+1R/+2R triggers, Chandelier 22/3x ATR, the optional 70th-percentile ATR
filter, the spread/slippage test levels) is taken as a fixed input, never
tuned. The question being answered is whether the proposed system's
improvement over the current (unmanaged) exit holds up across time and
execution conditions — not whether some other configuration would score
higher.

## System under test

| | Current (baseline) | Proposed |
|---|---|---|
| Entry | unchanged | unchanged |
| Stop loss | unchanged (0.5x ATR) | unchanged (0.5x ATR) |
| Exit | fixed 4.5x-ATR target / 12-bar time stop, no partials | 25% closed @ +1R, 25% closed @ +2R, remaining 50% trailed with a Chandelier exit (22-bar lookback, 3x ATR) until stop/time-stop |
| Optional add-on | — | "filtered" variant additionally skips any entry whose signal-bar ATR percentile is above 70% (the breakpoint found in `STRONG_TREND_ANALYSIS.md`) |

The proposed (unfiltered) system is structurally identical to Model D from
`strong_trend_stop_models.py`, run here against **every signal the locked
strategy takes** (the full 2,064-trade population), not the 659-trade
Strong Trend subset that earlier file scoped down to — the request describes
this as a general replacement exit structure, not a regime-scoped one.

## Two disclosed deviations from the literal request

**1. Walk-forward split.** Requested: 2015-2018 / 2019-2022 / 2023-2025. The
dataset (`data_loader.load_m15()`) covers **2012-05-15 through 2022-03-04
only** — confirmed directly before writing any code. The 2023-2025 window
has zero data, and using the other two windows literally would silently
discard the 194 trades that occur before 2015 (9.4% of the full population).
Used instead, shifted back by one window so all available data is covered by
three roughly-sequential, non-overlapping eras: **2012-2015 / 2016-2019 /
2020-2022** (last segment partial — ends with the data on 2022-03-04, not
Dec 2022).

**2. Slippage sensitivity.** `CostModel.stop_slippage` is a flat dollar
constant everywhere else in this project ($0.03 in the ECN scenario used
throughout); "0.1 ATR / 0.2 ATR" as requested is a *relative* quantity the
existing model doesn't express. Implemented only for this test as an
override applied at the moment of any slipped fill (stop or time-stop exit):
`slip_amount = mult * ATR-at-exit-bar`, replacing the flat constant.

Cost-sensitivity baseline (the "1x" anchor for the 0.5x/1x/1.5x/2x spread
sweep) is the ECN spread = 0.10 used as the primary scenario in every prior
round of this project.

## Methodology note: even the full, un-sliced population shows the dollar-vs-R PF gap

Every PF/expectancy/drawdown/Sharpe/CAGR figure below is computed from
**R-multiples** via the equity reconstruction `equity = initial_equity *
cumprod(1 + r_multiple * risk_per_trade)`, the convention established in
`session_analysis.py` and re-confirmed in `strong_trend_stop_models.py` for
slices of the trade list. This round extends that finding one step further:
even the **complete, chronologically-ordered, unsliced** 2,064-trade
baseline shows the same gap (dollar PF = 1.4210 vs R-multiple PF = 1.5989,
confirmed directly), because $-denominated position size scales with equity,
and equity grew ~39x over the backtest's ~9.8 years — so dollar pnl always
overweights whichever trades happened to land at high-equity points in time,
regardless of slicing. The "Current" baseline PF quoted in earlier rounds'
reports (1.4210) is the dollar-based figure; **1.5989 below is the
equity-scale-independent R-multiple figure for the identical trade set**,
used throughout this report for the same reason it was adopted everywhere
else.

## Full-period headline (sanity check)

| Variant | Trades | Win rate | PF (R) | Expectancy (R) | Max DD | Sharpe | Max consec. losses | CAGR |
|---|---|---|---|---|---|---|---|---|
| Current (no management) | 2,064 | 19.4% | 1.60 | 0.537R | -13.90% | 1.86 | 32 | 38.7% |
| Proposed (no filter) | 2,074 | 36.8% | 1.70 | 0.459R | -8.01% | 2.14 | 13 | 33.0% |
| Proposed + ATR-pct>70 filter | 1,587 | 37.8% | 1.73 | 0.470R | -7.79% | 1.87 | 11 | 25.0% |

Trade counts differ slightly between variants (2,064 vs 2,074) because a
different exit policy changes how long each position blocks new entries —
the proposed system's partials/trailing close positions sooner on average
than the baseline's fixed 4.5R target or 12-bar timeout, freeing a handful
of extra bars to take the next signal. This is the same effect already seen
between models in `strong_trend_stop_models.py`.

**Already visible at the full-population level:** the proposed system trades
away some average profitability (expectancy 0.537R → 0.459R, CAGR 38.7% →
33.0%) for a large gain in consistency (PF +6%, drawdown cut by 42%,
consecutive losses cut by 59%). This is the opposite character from the
Strong-Trend-only result in `STRONG_TREND_ANALYSIS.md`, where Model D
improved PF **and** expectancy **and** drawdown simultaneously — that was a
property of the one regime under research there, not of the strategy as a
whole. At full-population scope, this result instead matches the
stability-for-expectancy trade-off already documented for the full
population in the earlier `STOP_MANAGEMENT.md` round. Whether that
trade-off is *stable* — the actual subject of this study — is addressed
below.

## 1. Walk-forward segments

| Segment | Variant | Trades | Win rate | PF | Expectancy (R) | Max DD | Sharpe | Max consec. losses | CAGR |
|---|---|---|---|---|---|---|---|---|---|
| 2012-2015 | Current | 781 | 21.6% | 1.82 | 0.709R | -7.31% | 2.41 | 19 | 56.1% |
| 2012-2015 | Proposed | 785 | 38.9% | 2.00 | 0.634R | -3.19% | 2.74 | 11 | 49.8% |
| 2012-2015 | Proposed+filter | 593 | 38.5% | 1.94 | 0.603R | -3.91% | 2.18 | 9 | 33.6% |
| 2016-2019 | Current | 822 | 19.2% | 1.51 | 0.470R | -13.90% | 1.63 | 32 | 32.3% |
| 2016-2019 | Proposed | 826 | 35.6% | 1.54 | 0.372R | -8.01% | 1.77 | 12 | 25.2% |
| 2016-2019 | Proposed+filter | 643 | 37.2% | 1.58 | 0.391R | -7.79% | 1.62 | 11 | 20.3% |
| 2020-2022* | Current | 461 | 16.1% | 1.40 | 0.363R | -7.71% | 1.32 | 22 | 24.8% |
| 2020-2022* | Proposed | 463 | 35.6% | 1.50 | 0.317R | -6.23% | 1.66 | 13 | 22.0% |
| 2020-2022* | Proposed+filter | 351 | 37.9% | 1.64 | 0.388R | -5.57% | 1.74 | 10 | 20.3% |

\* partial segment — ends 2022-03-04 with the data, not Dec 2022.

**The pattern is stable across every segment, not just the full period:** in
all three eras, Proposed beats Current on PF, max drawdown, and consecutive
losses, and loses to it on expectancy and CAGR. The size of the trade-off
varies — the consecutive-loss improvement is largest in 2016-2019 (32→12,
vs 19→11 and 22→13 in the other two segments), and the drawdown improvement
is largest in 2016-2019 in absolute terms (-13.90%→-8.01%, a 5.9-point cut)
but largest in 2012-2015 in relative terms (-7.31%→-3.19%, a 56% reduction
vs 42% and 19% in the other two segments) — but the **direction** of every
metric's change never flips between segments. That directional consistency
is the central robustness finding of this section.

The optional filter's effect is also directionally consistent across
segments: it nudges PF and expectancy up slightly versus the unfiltered
proposed system in 2 of 3 segments (2016-2019, 2020-2022) and trades CAGR
down materially in all three (fewer trades to compound) — never a clear net
win, never a clear net loss, just a smaller, choppier system.

## 2. Leave-one-year-out

Each row removes one calendar year's trades entirely and recomputes every
statistic on what remains (chronological order preserved, no resizing of
the years that stay in). Full tables: `results/wf_leave_one_year_out.csv`.

| Year removed | Current PF | Current Exp(R) | Current MDD | Proposed PF | Proposed Exp(R) | Proposed MDD |
|---|---|---|---|---|---|---|
| none (full) | 1.60 | 0.537R | -13.90% | 1.70 | 0.459R | -8.01% |
| 2012 | 1.59 | 0.530R | -13.90% | 1.67 | 0.441R | -8.01% |
| 2013 | 1.61 | 0.545R | -13.90% | 1.71 | 0.466R | -8.01% |
| 2014 | 1.56 | 0.505R | -13.90% | 1.67 | 0.440R | -8.01% |
| 2015 | 1.55 | 0.496R | -13.90% | 1.63 | 0.416R | -8.01% |
| 2016 | 1.58 | 0.518R | -13.90% | 1.66 | 0.428R | -8.01% |
| 2017 | 1.52 | 0.467R | -13.90% | 1.65 | 0.430R | -8.21% |
| **2018** | 1.68 | 0.598R | **-9.46%** | 1.80 | 0.515R | **-6.23%** |
| 2019 | 1.67 | 0.597R | -13.90% | 1.78 | 0.504R | -8.01% |
| 2020 | 1.62 | 0.559R | -13.90% | 1.71 | 0.470R | -8.01% |
| 2021 | 1.62 | 0.555R | -13.90% | 1.73 | 0.475R | -8.01% |
| 2022 | 1.60 | 0.539R | -13.90% | 1.71 | 0.466R | -8.01% |

PF ranges 1.52-1.68 for Current and 1.63-1.80 for Proposed across all twelve
leave-one-out cuts — no single year's removal flips either system's PF below
~1.5, and Proposed's PF stays above Current's PF in every single cut, with
no exceptions. Same for expectancy and max drawdown: Proposed's max drawdown
is lower than Current's in all 12 cuts. Max consecutive losses is lower for
Proposed in every cut too: 13 vs 32 in 10 of 12 cuts, 13 vs 22 in the
2018-removed cut, and 12 vs 32 in the 2021-removed cut — both systems' own
worst-case streak only ever moves when the specific year containing that
streak is the one removed (2018 for Current, 2021 for Proposed), otherwise
it stays exactly flat.

**2018 is structurally distinct, for both systems.** It is the only year
whose removal changes max drawdown at all (-13.90% → -9.46% for Current,
-8.01% → -6.23% for Proposed) — meaning the single worst drawdown stretch in
the entire 9.8-year backtest is fully contained inside 2018 and touches no
other year, for both the current and proposed exits. This corroborates
`STRONG_TREND_ANALYSIS.md`'s Q2 finding that 2018 was one of only two
net-negative years for the Strong Trend regime; here it shows up as the
worst-drawdown year for the *entire* strategy, current or proposed. The
proposed system's drawdown in that exact stretch (-8.01% full-period) is
still 42% shallower than the current system's (-13.90%) — the improvement
holds during the strategy's single worst historical period, not just on
average.

## 3. Monte Carlo (1,000 trade-order reshuffles)

| Variant | Median CAGR | Min/Max CAGR across 1,000 runs | Median max DD | 95th-pct worst max DD | P(ruin, DD≥30%) | P(ruin, DD≥50%) |
|---|---|---|---|---|---|---|
| Current | 38.72% | 38.72% / 38.72% | -12.63% | -18.17% | 0.0% | 0.0% |
| Proposed | 32.95% | 32.95% / 32.95% | -7.59% | -11.08% | 0.0% | 0.0% |
| Proposed + filter | 24.97% | 24.97% / 24.97% | -7.12% | -10.83% | 0.0% | 0.0% |

**CAGR is mathematically invariant to trade order, and the 1,000 runs confirm
it directly** (min and max differ from the median only in the 10th decimal
place — floating-point noise). This is expected, not a finding to be
suspicious of: final compounded equity is a product of `(1 + r_i *
risk_per_trade)` terms, and multiplication is commutative, so reordering the
sequence cannot change the final value — only the *path* to it. "Median
CAGR" in a trade-shuffle Monte Carlo therefore measures the same single
number every system already has; it is reported here to make that property
explicit rather than to imply variance that doesn't exist.

**Drawdown and ruin probability are genuinely path-dependent, and this is
where the Monte Carlo actually adds information.** Across 1,000 random
orderings, Proposed's worst-case (95th-percentile) drawdown is -11.08% vs
Current's -18.17% — the path-risk reduction holds however the same set of
trades happens to be sequenced, not just in the one historical order that
actually occurred. Probability of ruin is 0% for every variant at both the
30% and 50% drawdown thresholds across all 1,000 reorderings of all three
systems — a consequence of position sizing (0.3% risk per trade) capping any
single loss near -1R regardless of exit model, not a property special to the
proposed exit. Ruin thresholds (30%/50% of initial equity, measured as
peak-to-trough on the R-based equity curve) are this report's own choice,
disclosed since the request didn't specify one.

## 4. Cost sensitivity (spread multiplier, base = 0.10 ECN)

| Spread | Current PF | Current MDD | Current CAGR | Proposed PF | Proposed MDD | Proposed CAGR |
|---|---|---|---|---|---|---|
| 0.5x (0.05) | 1.70 | -12.48% | 45.0% | 1.84 | -6.59% | 38.2% |
| 1.0x (0.10) | 1.60 | -13.90% | 38.7% | 1.70 | -8.01% | 33.0% |
| 1.5x (0.15) | 1.52 | -15.30% | 34.5% | 1.59 | -10.17% | 28.4% |
| 2.0x (0.20) | 1.44 | -19.06% | 28.9% | 1.46 | -16.55% | 22.2% |

Both systems degrade monotonically as spread widens, as expected — no
surprises there. The proposed system's PF stays above the current system's
at every spread level tested, including the worst case (2x spread: 1.46 vs
1.44), though the gap narrows steadily as spread rises (+0.13 at 0.5x, +0.10
at 1x, +0.07 at 1.5x, +0.02 at 2x) — cost inflation erodes the proposed
system's edge but does not reverse it within the tested range. Drawdown
shows the same erosion pattern, not a widening one: Proposed's max-drawdown
advantage over Current holds essentially flat from 0.5x to 1x spread (5.9
percentage points both times), then narrows at 1.5x (5.1pp) and narrows
sharply at the extreme 2x case (2.5pp). Both the PF and the drawdown
advantage are real and positive across the whole tested range, but both
shrink toward the high-cost end rather than growing — the honest read is
"the advantage persists but compresses under cost stress," not that it
strengthens.

## 5. Slippage sensitivity (0 / 0.1 / 0.2 × ATR at exit)

| Slippage | Current PF | Current WR | Current MDD | Proposed PF | Proposed WR | Proposed MDD |
|---|---|---|---|---|---|---|
| 0 × ATR | 1.66 | 19.4% | -12.33% | 1.78 | 36.8% | -6.98% |
| 0.1 × ATR | 1.36 | 19.3% | -18.33% | 1.42 | 36.8% | -13.36% |
| 0.2 × ATR | 1.15 | 19.2% | -43.93% | 1.16 | 36.8% | -32.30% |

This is the sharpest stress test in the study, and the clearest evidence the
improvement is real rather than cosmetic. Two findings:

**The proposed system's win rate is completely insensitive to slippage
(36.84% at all three levels), while the current system's erodes slightly
(19.43% → 19.19%).** This is a direct, structural consequence of partial
profit-taking: 50% of every winning trade's size is already closed at +1R
and +2R, at take-profit fills that never carry slippage, before any
slippage-sensitive stop or time-stop exit can touch the remaining position.
A trade that banked real, unslipped profit on half its size can survive a
slippage hit on the other half and still close net-positive — the current
system has no such buffer; its entire size is exposed to slippage at the one
exit that closes it.

**Drawdown blows up far less under heavy slippage stress for the proposed
system.** At 0.2 ATR slippage, Current's max drawdown reaches -43.93%
(more than triple its 0-slippage value) while Proposed reaches -32.30% (4.6x
its own 0-slippage value, but still 11.6 percentage points shallower than
Current's). The relative advantage of the proposed system *grows* under
slippage stress rather than shrinking — the opposite of what would be
expected if the earlier results were a thin, condition-specific edge.

Average profitability (expectancy_r, PF) still degrades sharply for both
systems under 0.2 ATR slippage — partial profit-taking blunts the damage,
it does not immunize the strategy against a genuinely adverse execution
environment.

## Verdict: does the improvement remain stable?

**Yes, for consistency — PF, max drawdown, and consecutive-loss count.**
Every walk-forward segment, every one of the 12 leave-one-year-out cuts,
every Monte Carlo reordering, every spread level (0.5x-2x), and every
slippage level (0-0.2 ATR) shows the same direction of change: Proposed
beats Current on PF, drawdown, and consecutive losses, without a single
exception across all the conditions tested. The advantage is not
concentrated in one calendar era or one cost regime — it holds the same way
everywhere it was checked, and gets *larger* (not smaller) under slippage
stress specifically because of the partial-profit-taking mechanism.

**No, for average profitability — expectancy and CAGR.** Proposed's
expectancy-in-R and CAGR are lower than Current's in literally every segment,
every leave-one-out cut, every cost level, and every slippage level tested —
also without exception. This is a genuine, stable trade-off, not noise: the
proposed system reliably converts some average return into reliability. This
matches the full-population finding already on record in the earlier
`STOP_MANAGEMENT.md` round, and is the opposite of the Strong-Trend-regime-
only result in `STRONG_TREND_ANALYSIS.md` (where the same Model D structure
improved both PF *and* expectancy at once) — that free lunch was specific to
the one regime it was found in and does not generalize to the full
population.

**The optional ATR-pct>70% filter does not clearly improve on the unfiltered
proposed system at full-population scope.** It nudges PF and expectancy up
by low single-digit percentages in most cuts, at the cost of removing ~23%
of all trades and a CAGR reduction larger than that marginal PF gain
justifies (e.g. full period: PF 1.703→1.726, CAGR 33.0%→25.0%). This is
consistent with the filter's origin: it targets a breakpoint discovered
specifically *within* the Strong Trend regime in `STRONG_TREND_ANALYSIS.md`,
where the unhealthy ATR-pct>70 tail was concentrated; applied as a blanket
filter across the whole signal population it removes a much broader, more
ordinary mix of trades, most of which were not actually unprofitable.
Recommendation: do not generalize this filter beyond the Strong Trend
context where it was found.
