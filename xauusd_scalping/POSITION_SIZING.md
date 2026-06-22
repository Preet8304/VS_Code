# Position-Sizing Comparison

Scope, per the request: **entries, exits, and stop-loss logic are completely
unchanged** -- this is a position-sizing study only, run against the exact
same trade-by-trade outcomes the locked strategy has produced throughout
this project. No entry filter, stop distance, target, or trailing rule is
touched anywhere in this file.

## Why no backtest replay was needed

The locked strategy fixes the stop distance per trade and sizes as
`size_oz = risk_dollars / stop_dist`. That makes every trade's R-multiple

```
r_multiple = pnl / risk_dollars = (exit_price - entry_price) / stop_dist
```

**independent of position sizing** -- `risk_dollars` and `size_oz` cancel
out of the ratio. So instead of re-running the bar-by-bar simulator eight
times, this study reuses the single already-validated, chronologically
sorted, 2,064-trade R-multiple sequence in
`results/trade_regime_full_ecn.csv` (full signal population, ECN costs --
the same trade list `WALKFORWARD_ROBUSTNESS.md` validated) and reconstructs
a dollar equity curve per sizing model via
`equity *= (1 + r_multiple * risk_fraction)`, varying only
`risk_fraction`. Source: `position_sizing_models.py`.

System under test: 2,064 trades, 2012-05-17 -> 2022-03-04 (9.80 years),
starting equity $10,000 in every model (same convention as
`backtest.py`'s `RiskModel`). For context, the project's actual locked
default risk-per-trade is 0.3%, bracketed between the two lowest
fixed-fractional rows tested below.

## The eight models (plain, disclosed, non-tuned constants -- "do not
optimize" means these are archetypes being compared, not parameters being
searched)

| Model | Rule |
|---|---|
| Fixed fractional 0.25% / 0.5% / 1% | Constant % of current equity, every trade. |
| Volatility-adjusted | Base 0.5%, multiplied by `median(atr_pct_sig) / atr_pct_sig[trade]`, clipped to [0.5x, 1.5x]. Larger size in calm conditions, smaller in volatile ones. Median (0.56) is the sample's own median, used only as a calibration anchor, not fit. |
| Fractional Kelly 0.25x / 0.5x | `f* = p - (1-p)/b` computed once from the full 2,064-trade sample: p=19.428% win rate, avg_win=7.374R, avg_loss=1.112R, b=6.631, **f\*=7.278%**. 0.25x -> 1.819% risk/trade, 0.5x -> 3.639% risk/trade. |
| Anti-Martingale | Base 0.5%, **1.5x base (0.75%)** on any trade entered while equity is at an all-time high (no open drawdown); base otherwise. Boosted risk fired on 199 of 2,064 trades (9.6%). |
| Drawdown-aware | Base 0.5%, cut 50% (to 0.25%) once 5 consecutive losses have occurred, restored to base the instant a winning trade resets the streak counter. Reduced-risk rate applied on 690 of 2,064 trades (33.4% -- this strategy's 19.4% win rate makes 5-loss streaks common). |

**Disclosed limitation on Kelly:** `f*` is a static, full-sample estimate
that uses the entire history at once (look-ahead). That is fine for
comparing sizing archetypes against each other here, but it is not a
walk-forward-safe estimate and should not be read as a live-deployable
number.

## Headline per-model results (real chronological order, no shuffling)

| Model | Final equity | CAGR | Max DD | Ulcer Index | Sharpe | MAR | Longest recovery | Still unrecovered at end |
|---|---|---|---|---|---|---|---|---|
| Fixed 0.25% | $146,972 | 31.57% | -11.69% | 3.05 | 1.857 | 2.70 | 392d | 236d |
| Fixed 0.5% | $1,842,882 | 70.32% | -22.35% | 6.09 | 1.857 | 3.15 | 392d | 236d |
| Fixed 1% | $184,118,675 | 172.52% | -40.69% | 12.11 | 1.857 | 4.24 | 399d | 236d |
| Volatility-adjusted | $2,539,644 | 75.99% | -23.72% | 7.34 | 1.776 | 3.20 | 621d | 236d |
| Kelly 0.25x | $103.5B | 420.09% | -63.13% | 21.85 | 1.856 | 6.65 | 620d | 236d |
| Kelly 0.5x | $1.19 quadrillion | 1250.32% | -88.77% | 44.91 | 1.855 | 14.08 | 1190d | 236d |
| Anti-Martingale | $2,549,596 | 76.06% | -22.56% | 6.28 | 1.861 | 3.37 | 392d | 236d |
| Drawdown-aware | $734,966 | 55.06% | -18.54% | 5.86 | 1.764 | 2.97 | 443d | 236d |

Max DD and MAR use the same trade-by-trade equity-curve convention as
every prior report in this project (`max_drawdown_pct`). Ulcer Index,
Sharpe, and recovery-period are calendar-time concepts, computed on the
same daily-resampled (`resample('1D').last().ffill()`) equity curve this
project's Sharpe has always used -- a deliberate methodology choice since
Ulcer/recovery are inherently about elapsed calendar time, not raw trade
count. All eight models are still sitting inside the same not-yet-
recovered final drawdown as of the data's last bar (236 days and counting
as of 2022-03-04) -- that figure is reported separately from "longest
recovery," which only counts *completed* peak-to-new-high episodes.

## Findings

**1. Sharpe barely moves across the constant-fraction models, and that's
expected, not a bug.** Fixed 0.25% / 0.5% / 1% and both Kelly fractions all
land within 1.857 +/- 0.002 despite final equity spanning six orders of
magnitude. For a small, constant per-trade risk fraction, daily returns
scale almost linearly with the fraction, and Sharpe (mean/std of returns)
is scale-invariant under linear scaling -- it measures the *shape* of the
underlying trade-timing/R-multiple distribution, not the danger of the
sizing level. **Sharpe should not be used alone to rank sizing models in
this study** -- Max DD, Ulcer Index, MAR, and the Monte Carlo ruin
probabilities below are where the real differences show up.

**2. Kelly sizing is the textbook-optimal grower and the practically worst
choice here.** Kelly 0.25x and 0.5x post the highest CAGR and the highest
MAR ratio of all eight models (6.65 and 14.08) -- but get there via -63%
and -89% max drawdowns. The Monte Carlo section below shows this isn't a
one-off: across 1,000 reshuffles, Kelly 0.25x hits a >=30% drawdown in
100% of runs and a >=50% drawdown in 88.3% of runs; Kelly 0.5x hits >=50%
drawdown in 100% of runs. **The single best headline number (MAR) belongs
to the model no real account could survive trading.** This is the
clearest "no free lunch" result in the study: ranking sizing models by
MAR or CAGR alone, without looking at drawdown distribution, would pick
the worst possible answer.

**3. Anti-Martingale adds no real edge over flat fixed-fractional at the
same base risk.** Anti-Martingale (base 0.5%, 1.5x at equity highs) posts
CAGR 76.06% / MDD -22.56% versus flat Fixed 0.5%'s CAGR 70.32% / MDD
-22.35% -- a marginal, not decisive, difference, and Monte Carlo prob of
>=30% drawdown is essentially identical (3.3% vs 3.1%). "Increase risk at
equity highs" only pays off if winning streaks predict more winning
streaks; this strategy's trade sequence shows no such equity-curve
momentum, so boosting size on 9.6% of trades neither meaningfully helps
nor meaningfully hurts.

**4. Drawdown-aware sizing is the one model that meaningfully changes the
risk profile, in the direction that matters.** Versus the same 0.5%-base
group: Drawdown-aware cuts max drawdown to -18.54% (vs -22.35% to -23.72%
for the other three 0.5%-base models) and, more importantly, cuts the
Monte Carlo probability of a >=30% drawdown to 0.3% -- roughly 10x lower
than flat Fixed 0.5% (3.1%) and roughly 26x lower than Volatility-adjusted
(7.9%). The cost is real and disclosed: CAGR drops to 55.06%, about 15
points below flat Fixed 0.5%'s 70.32%. This is a genuine, non-free
trade-off, not an illusion -- the rule earns its lower tail risk by sizing
down during the (frequent, given a 19.4% win rate) losing streaks where a
flat-risk account keeps compounding losses at full size.

**5. Volatility-adjusted sizing, as calibrated here, is roughly a wash
against flat 0.5%.** CAGR is somewhat higher (75.99% vs 70.32%) but so is
max drawdown (-23.72% vs -22.35%) and the Monte Carlo >=30%-drawdown
probability (7.9% vs 3.1%) -- MAR (3.20 vs 3.15) is essentially tied. The
[0.5x, 1.5x] clip band tested is too narrow to meaningfully change the
risk profile in either direction; it is not shown to be either better or
worse than simply picking a flat fraction.

## Monte Carlo (1,000 trade-order shuffles per model)

| Model | Median CAGR | CAGR std | Median DD | p95-worst DD | P(DD>=30%) | P(DD>=50%) |
|---|---|---|---|---|---|---|
| Fixed 0.25% | 31.57% | ~0.0pp | -10.60% | -15.34% | 0.0% | 0.0% |
| Fixed 0.5% | 70.32% | ~0.0pp | -20.31% | -28.59% | 3.1% | 0.0% |
| Fixed 1% | 172.52% | ~0.0pp | -37.13% | -49.64% | 92.0% | 4.9% |
| Volatility-adjusted | 75.99% | ~0.0pp | -22.59% | -31.53% | 7.9% | 0.0% |
| Kelly 0.25x | 420.09% | ~0.0pp | -58.35% | -72.80% | 100.0% | 88.3% |
| Kelly 0.5x | 1250.32% | ~0.0pp | -85.21% | -94.06% | 100.0% | 100.0% |
| Anti-Martingale | 74.51% | 2.04pp | -20.52% | -28.80% | 3.3% | 0.0% |
| Drawdown-aware | 56.05% | 2.56pp | -16.45% | -23.28% | 0.3% | 0.0% |

**The invariance/path-dependence split lands exactly where the math
predicts.** Fixed-fractional, Volatility-adjusted, and both Kelly
fractions size each trade from that trade's own fixed attribute (a
constant, or that trade's own `atr_pct_sig`) -- so under any reordering,
every trade still carries the same `(r_multiple, risk_fraction)` pair, and
final compounded equity is the product of the same set of `(1 + r*f)`
factors regardless of order (multiplication commutes). Their Monte Carlo
CAGR std is ~1e-14 percentage points -- floating-point noise, not real
variance; median/min/max CAGR are identical to 10+ significant figures.
Anti-Martingale and Drawdown-aware are different by construction: their
risk fraction depends on running state (the equity peak, the
consecutive-loss counter) that is itself a product of trade order, so
reshuffling genuinely changes which risk fraction lands on which
R-multiple. Their CAGR std (2.04pp and 2.56pp) and CAGR range
(Anti-Martingale 68.36%-80.58%, Drawdown-aware 46.09%-64.67%) are real,
not noise -- the only two models in this study whose long-run outcome
depends on trade *sequence*, not just the *multiset* of trades.

Max drawdown, by contrast, varies by shuffle order for **every** model,
including the six that have invariant CAGR -- drawdown is a path
statistic (it depends on the running maximum), so reordering the same
factors changes which losses cluster together even when the final product
is unchanged. This is why even Fixed 0.25% shows a Monte Carlo
median-drawdown of -10.60% (vs -11.69% in the actual historical order) and
a p95-worst case of -15.34%.

Sharpe, Ulcer Index, and recovery period are not recomputed per shuffle.
These are calendar-time concepts (the daily-resample convention above
requires real timestamps), and a reshuffled trade order keeps each
trade's original timestamp while changing its position in the sequence --
producing an artifact calendar with duplicated/out-of-order dates, not a
coherent alternate history. Monte Carlo here reports CAGR and
drawdown-based statistics only, the same convention
`walkforward_robustness.py`'s Monte Carlo section already used. The
"years" denominator for every shuffle's CAGR is held fixed at the actual
9.80-year historical span, also matching that file's precedent.

## Verdict: which sizing approach gives the best risk-adjusted return?

**Not by single-metric ranking.** If you rank by MAR or CAGR alone, Kelly
0.5x wins (MAR 14.08) and Kelly 0.25x is second (MAR 6.65) -- but both
have an 88%+ Monte Carlo probability of losing half the account, which
makes "best risk-adjusted" by that ranking a misleading answer. Excluding
Kelly as operationally unviable (per the drawdown/ruin evidence above,
not per any tuning), the remaining six models split into two honest,
disclosed trade-offs rather than one clean winner:

- **Among the 0.5%-base family (Fixed 0.5%, Volatility-adjusted,
  Anti-Martingale, Drawdown-aware), Drawdown-aware gives up CAGR
  (55.06% vs 70-76% for the other three) in exchange for the only
  material reduction in tail risk in the entire study** -- max drawdown
  -18.54% vs -22.35%/-22.56%/-23.72%, and a 1,000-shuffle probability of a
  >=30% drawdown of 0.3% vs 3.1%/3.3%/7.9%. If the objective is capital
  preservation per unit of risk taken, **Drawdown-aware is the standout**
  -- it is the only mechanical rule tested that meaningfully changes the
  risk profile in a favorable direction, using a plain, non-tuned
  threshold (5 consecutive losses, 50% cut) exactly as specified.
- **If the objective is MAR/CAGR within the same risk band, Fixed 0.5%,
  Volatility-adjusted, and Anti-Martingale are statistically
  indistinguishable** (MAR 3.15 / 3.20 / 3.37) -- none of the "smarter"
  adaptive rules tested here clears a real bar over plain flat-fractional
  sizing once replayed with full state.
- **Fixed 0.25% is the single lowest-risk choice in absolute terms**
  (lowest max drawdown of any non-Kelly model, -11.69%, and zero
  Monte Carlo probability of a >=30% drawdown across 1,000 shuffles) but
  at the cost of the lowest absolute compounding rate (31.57% CAGR) of
  any non-trivial model.

**Overall: Drawdown-aware sizing (base 0.5%, -50% after 5 consecutive
losses) is the best risk-adjusted choice of the eight tested.** It is not
the highest CAGR, nor even the highest single-number MAR -- Anti-
Martingale and Volatility-adjusted both edge it narrowly on MAR, and Kelly
dominates MAR outright. But it is the only model that lowers *both* max
drawdown *and* Monte Carlo probability of ruin relative to the
un-adapted base case while still compounding at a strong absolute rate
(55% CAGR), and it does so through a directly interpretable, completely
mechanical, non-tuned rule -- consistent with "do not optimize." Anti-
Martingale, by contrast, is shown to add no real value over flat
fixed-fractional sizing at the same base risk -- a genuine negative result
worth stating plainly rather than papering over.
