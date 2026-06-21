# Strong Trend + High Volatility Regime — Deep Dive

Read-only regime research, produced by `strong_trend_analysis.py` (per-trade
breakdown) and `strong_trend_stop_models.py` (stop-management simulation).
**No entry, sizing, or locked-parameter change anywhere in this file.**
Scope is narrowed to one regime only: "Strong Trend" in
`regime_analysis.py`'s 2x2 grid (ADX(14) >= 25 **and** ATR-percentile >=
0.5) — 659 of the 2,064 total trades, the regime already flagged there as
both the largest (32% of all trades) and weakest (PF 1.22) of the four.

## Methodology note: PF is reported in R-multiples, not dollars, throughout this file

The headline "PF 1.22" for this regime in `REGIME_ANALYSIS.md` was computed
from raw dollar `pnl`. That is the right number for "what this regime
actually contributed in real dollars given the real historical equity
path," but it is the **wrong** number for comparing sub-slices of it (by
year, by direction, by ATR/ADX bin) against each other — those slices are
not the full chronological sequence from the very first trade, so their
dollar `pnl` figures were generated against whatever the *real* historical
equity happened to be at each trade's own point in time, and summing them
directly into a PF ratio mixes trades from very different equity scales.
This is exactly the bias `SESSION_ANALYSIS.md` already found and fixed for
by-year **drawdown**; it turns out to affect by-year/by-bin **PF** too.
Direct check, same 659 trades: **dollar-pnl PF = 1.2152, R-multiple PF =
1.4018.** Every PF figure below uses R-multiples (equity-scale-independent)
for this reason; dollar figures (loss totals, expectancy in $) are kept
only as supplementary, real-money color, never as a PF numerator/
denominator.

The full per-trade record (ADX, ATR-percentile, EMA50 slope, R-multiple,
MFE, MAE, direction, exit reason, bars held) for all 659 trades is saved at
`results/strong_trend_trades.csv`.

## 1. Do losses come from longs, shorts, or both?

| Direction | Trades | Win rate | PF (R) | Avg R | Losing trades | Loss $ |
|---|---|---|---|---|---|---|
| Long | 350 | 20.0% | 1.55 | 0.486R | 280 | $96,327 |
| Short | 309 | 16.5% | 1.24 | 0.221R | 258 | $83,192 |

**Both.** Neither side is purely responsible — both longs and shorts in
this regime are net profitable in R-terms, but shorts are meaningfully
weaker on every metric (lower win rate, PF 1.24 vs 1.55, less than half the
per-trade R of longs). Loss-dollar totals are roughly proportional to trade
count on each side (96k/280 long losers ≈ $344/loser vs 83k/258 short
losers ≈ $322/loser) — losses are not disproportionately sized on one side,
just somewhat more frequent and harder-fought on the short side.

## 2. Are losses concentrated in specific years?

| Year | Trades | Win rate | PF (R) | Avg R | Loss $ |
|---|---|---|---|---|---|
| 2012 | 46 | 17.4% | 1.50 | 0.449R | $1,395 |
| 2013 | 82 | 20.7% | 1.61 | 0.523R | $3,208 |
| 2014 | 66 | 24.2% | 1.91 | 0.764R | $3,705 |
| 2015 | 70 | 20.0% | 1.38 | 0.334R | $6,604 |
| 2016 | 46 | 21.7% | 1.82 | 0.701R | $7,570 |
| 2017 | 37 | 21.6% | 2.07 | 0.966R | $11,488 |
| **2018** | 93 | 12.9% | **0.85** | **-0.145R** | $37,231 |
| 2019 | 81 | 19.8% | 1.40 | 0.362R | $32,653 |
| 2020 | 55 | 18.2% | 1.48 | 0.414R | $24,197 |
| **2021** | 74 | 10.8% | **0.77** | **-0.221R** | $46,084 |
| 2022* | 9 | 22.2% | 2.41 | 1.163R | $5,384 |

\* partial year, data ends 2022-03-04.

**Yes, sharply.** 2018 and 2021 are the only two years where this regime
loses money on a risk-normalized basis (PF below 1.0, negative average R).
Together they hold $83,315 of the regime's $179,519 total loss dollars —
**46% of all losses concentrated in 2 of 11 years (18% of the calendar
span)**. Every other year is solidly profitable (PF >= 1.38, most well
above). This matches `SESSION_ANALYSIS.md`'s independent finding that 2018
is the strategy's weakest year overall — Strong Trend's 2018 weakness is
not a regime-specific story, it is largely that year's general weakness
showing up inside this regime too. 2021 having no such full-strategy
flag elsewhere makes it the more regime-specific of the two soft years.

## 3. Do losers cluster around extremely high ATR percentiles?

| | Mean | Median | P75 | P90 | Max |
|---|---|---|---|---|---|
| Losers' ATR-pct | 0.697 | 0.700 | 0.780 | 0.850 | 0.900 |
| Winners' ATR-pct | 0.692 | 0.680 | 0.780 | 0.850 | 0.900 |

**No, not really.** The ATR-percentile distributions of losers and winners
are almost indistinguishable (means within 0.005 of each other, identical
P75/P90/max). Losing trades in this regime are not occurring at
meaningfully more extreme volatility than winning trades are. Section 4
below shows the real volatility effect lives in the *aggregate* PF-by-bin
relationship (a population-level pattern), not in a within-regime skew of
which individual trades happen to lose.

## 4. ATR-percentile comparison: 0-70 / 70-85 / 85-95 / 95-100

Two cuts, both holding ADX >= 25 (the regime's trend condition) fixed and
varying only the volatility axis — the natural complementary slice to ask
"where does volatility start to hurt, inside trending markets":

**(a) Broader trending universe** (ADX>=25, both Quiet Trend + Strong Trend
grid cells, n=952 — lets the bottom bin include ATR-pct below the
regime's own 0.5 floor too):

| ATR-pct bin | Trades | Win rate | PF (R) | Expectancy ($) |
|---|---|---|---|---|
| 0-70 | 618 | 20.9% | 1.79 | $175.03 |
| 70-85 | 251 | 17.1% | 1.24 | -$5.55 |
| 85-95 | 83 | 19.3% | 1.36 | $6.32 |
| 95-100 | 0 | — | — | — |

**(b) Within the Strong Trend regime itself** (n=659, already atr_pct>=0.5):

| ATR-pct bin | Trades | Win rate | PF (R) | Expectancy ($) |
|---|---|---|---|---|
| 50-70 | 325 | 19.1% | 1.54 | $121.56 |
| 70-85 | 251 | 17.1% | 1.24 | -$5.55 |
| 85-95 | 83 | 19.3% | 1.36 | $6.32 |
| 95-100 | 0 | — | — | — |

**The 95-100 bin is structurally empty in both cuts** — not an omission.
The strategy's own locked entry filter (`atr_pct_high=0.90`) never allows
an entry above the 90th ATR percentile, so no trade can ever land there.
This is the same kind of mechanical, by-construction finding as
`SESSION_ANALYSIS.md`'s 100%-overlap result.

## 5. ADX comparison: 20-25 / 25-30 / 30-40 / 40+

Mirror cut: holding ATR-pct >= 0.5 (the regime's volatility condition)
fixed, varying ADX.

**(a) Broader volatile universe** (ATR-pct>=0.5, both Strong Trend +
Volatile Range grid cells, n=1,253 — lets the bottom bin go below the
regime's own ADX 25 floor):

| ADX bin | Trades | Win rate | PF (R) | Expectancy ($) |
|---|---|---|---|---|
| 20-25 | 290 | 20.3% | 1.72 | $108.92 |
| 25-30 | 219 | 17.8% | 1.26 | $35.92 |
| 30-40 | 270 | 17.8% | 1.35 | $88.27 |
| 40+ | 170 | 20.0% | 1.67 | $40.81 |

(ADX<20 within this universe, n=304, not a requested bin: PF 1.93 — shown
for completeness only.)

**(b) Within the Strong Trend regime itself** (n=659, already ADX>=25):

| ADX bin | Trades | Win rate | PF (R) | Expectancy ($) |
|---|---|---|---|---|
| 25-30 | 219 | 17.8% | 1.26 | $35.92 |
| 30-40 | 270 | 17.8% | 1.35 | $88.27 |
| 40+ | 170 | 20.0% | 1.67 | $40.81 |

## Gradual decline or natural breakpoint?

**The ATR-percentile axis shows a genuine breakpoint, not gradual decay.**
PF holds steady and strong (1.54-1.79) everywhere below the 70th
percentile, then drops sharply (-20% to -31% relative) the instant the
70th-percentile line is crossed, and **stays at that same lower plateau**
(1.24-1.36) all the way to the structural ceiling at the 90th percentile —
it does not continue falling further into the tail. That flat-after-the-
cliff shape is the signature of a breakpoint, not a slope.

**The ADX axis shows no comparable breakpoint.** It is non-monotonic: PF
dips to its low point at 25-30 (the band immediately above the regime's own
entry boundary), then *recovers* at 30-40 and again at 40+ — the most
extreme trends in the dataset perform almost as well as the calmest ones.
There is no single ADX line above which performance reliably degrades.

**Conclusion: deterioration in this regime is driven by volatility, not by
trend strength.** The ATR-percentile breakpoint is the real, sharp,
reproducible signal; the ADX relationship is comparatively flat and noisy.

## Is a broad regime exclusion justified?

**No.** A blanket exclusion of the entire Strong Trend regime would throw
out its healthy lower half — the 50th-70th ATR-percentile slice alone is
325 trades (just under half the regime) at PF 1.54, in line with the rest
of the strategy. The actual underperformance is concentrated in a narrower
band: ATR-percentile above 70 specifically (251 of 659 trades, 38% of the
regime), where PF sits around 1.24-1.36 — still above breakeven, just
weaker than the regime's other three-fifths. Excluding the whole regime to
address a problem that is properly localized to its top volatility tier
would discard far more edge than it would remove. (This describes where the
existing data's natural break already falls; per "do not optimize
thresholds," no new fitted cutoff is being proposed.)

## Losing trades held >= 2 bars: how much was given back before stopping out

202 of the regime's 538 losing trades (37.5%) were held 2 or more bars.
Among those, the maximum favorable excursion reached before the eventual
stopout:

| | Mean | Median | P75 | P90 | Max |
|---|---|---|---|---|---|
| MFE (R) | 3.308 | 2.691 | 4.568 | 6.425 | 8.848 |

**92.1%** of these losers touched at least +1R of unrealized profit before
reversing into a loss; **70.3%** touched at least +2R. The median
slow-loser gave back 2.69R of paper profit on its way to closing flat or
negative. This is a large, real pool of "failed winners" — trades that were
genuinely working before the regime's late-trade volatility (per the
breakpoint finding above) gave the move back. It directly motivates testing
whether locking in some of that unrealized profit changes the regime's
economics.

## Stop-management simulation (same entries, evaluated in R-multiples)

Five models, replayed on the full chronological signal sequence (position
sizing pinned to the original 0.5x ATR stop distance throughout, identical
conservative same-bar tie-break convention as `stop_management.py`), then
filtered to the canonical 659-trade Strong Trend entry set for reporting.

| Model | Trades | Win rate | PF (R) | Expectancy/Avg R | Max DD | Max consec. losses |
|---|---|---|---|---|---|---|
| **Current** (baseline, no management) | 659 | 18.4% | 1.40 | 0.361R | -10.66% | 33 |
| A — breakeven after +1R | 657 | 12.8% | 1.52 | 0.328R | -8.66% | 40 |
| B — +0.5R lock after +2R | 657 | 39.4% | 1.54 | 0.361R | -7.39% | 12 |
| C — 25% @ +1R, breakeven on remainder | 657 | 45.8% | 1.38 | 0.225R | -8.15% | 12 |
| **D — 25% @ +1R, 25% @ +2R, trail remainder (Chandelier 22/3x)** | 657 | 34.7% | **1.59** | **0.394R** | **-6.79%** | **13** |
| E — 50% @ +1.5R, trail remainder (3x ATR) | 656 | 43.0% | 1.34 | 0.217R | -7.20% | 12 |

("Expectancy" and "Average R" are the same per-trade-mean-R quantity, as
requested — reported once.)

### Ranking

1. **Model D.** The only model that improves *both* PF (1.40 -> 1.59) and
   expectancy (0.361R -> 0.394R) over the unmanaged baseline simultaneously,
   while also cutting max drawdown by 36% (-10.66% -> -6.79%) and max
   consecutive losses by more than half (33 -> 13). Booking two small
   partials early and handing the remainder to a Chandelier trail
   specifically captures value from the "failed winners" pattern found
   above — this regime's losers very often had real profit on the table
   first.
2. **Model B.** PF improves to 1.54 with expectancy essentially flat (0.361R
   vs 0.361R, a wash) and the same dramatic loss-streak reduction (33 -> 12)
   as D, but without D's added expectancy gain or best-in-class drawdown.
3. **Model A.** PF improves to 1.52 but expectancy is given up (0.328R) and,
   counter-intuitively, the loss-streak count gets *worse* (40 vs 33) — the
   same pattern already documented in `STOP_MANAGEMENT.md`: a pure
   breakeven rule with no partial-booking converts some would-be small wins
   into small breakeven-or-negative exits, which can string together more
   loss-labeled trades even as PF rises.
4. **Model E.** Smoothest loss-streak profile (12) but the second-lowest
   expectancy (0.217R) of the five — taking 50% off the table this early
   gives up too much of the regime's larger winners.
5. **Model C.** Lowest PF (1.38, barely above baseline) and lowest
   expectancy (0.225R) of the five — a small 25% partial followed by a flat
   breakeven stop (no trailing) captures the least of what models D/E/B
   capture, for no compensating drawdown advantage over them.

### Does partial profit-taking plus trailing convert failed winners into positive expectancy?

**Yes, and more cleanly than in the full, unfiltered strategy.** In the
regime-wide stop-management round (`STOP_MANAGEMENT.md`), every management
variant traded away some expectancy for a higher PF — none beat the
baseline on both axes at once. Here, restricted to exactly the regime where
losers are shown above to give back large median MFE (2.69R) before
stopping out, **Model D beats the unmanaged baseline on every metric
reported**: higher PF, higher expectancy, lower drawdown, far fewer
consecutive losses. The mechanism is direct: a meaningful share of this
regime's "failed winners" get partially monetized at +1R/+2R before the
late-trade volatility (the ATR-percentile breakpoint documented above)
takes the rest of the move away — turning some trades that would have
closed flat or negative under the unmanaged baseline into trades with at
least some locked-in profit.

## Files produced

- `results/strong_trend_trades.csv` — full per-trade record for all 659
  Strong Trend trades (ADX, ATR-pct, EMA50 slope, R-multiple, MFE, MAE,
  direction, exit reason, bars held).
- `results/strong_trend_by_direction.csv`, `strong_trend_by_year.csv`,
  `strong_trend_atr_bins.csv`, `strong_trend_atr_bins_within.csv`,
  `strong_trend_adx_bins.csv`, `strong_trend_adx_bins_within.csv`,
  `strong_trend_slow_losers.csv` — every breakdown table above.
- `results/strong_trend_stop_models_summary.csv` — the 6-row stop-management
  table above.
