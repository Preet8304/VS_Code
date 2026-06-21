# Market-Regime Classification of Existing Trades

Read-only research, produced by `regime_analysis.py`. Every trade comes
from `audit.run_audit()` unchanged (same entries, same exits, same MFE/MAE
already validated in the original trade-by-trade audit). Three regime
inputs are computed at the **signal bar** (one bar before entry, the same
no-lookahead convention used everywhere else in this project):

- **ADX(14)** — standard Wilder trend-strength indicator, period 14 to
  match the project's existing `atr_period` rather than introduce a new
  number. Classified "trending" at the classic, textbook ADX ≥ 25
  threshold.
- **ATR percentile** — the strategy's own existing `atr_pct` field
  (100-bar lookback, already in `StrategyParams`). Split at the median
  (0.5) for "quiet" vs. "volatile" — the plainest possible split of an
  already-existing field, not a new fitted threshold.
- **EMA50 slope** — `ema(close, 50)` (an existing project constant; H1's
  `htf_ema_fast` is already 50) read on M15, expressed in ATR units over a
  14-bar window (matching ADX/ATR's own period). Reported descriptively per
  regime below, not used to draw the regime boundaries — the four named
  regimes name exactly two axes (trend strength × volatility), so the grid
  is ADX × ATR-percentile only.

## The four regimes (2×2 grid: ADX ≥ 25 × ATR-pct ≥ 0.5)

| Regime | Trades | Win rate | Profit factor | Expectancy/trade | Avg MAE (R) | Avg MFE (R) | Avg ADX | Avg ATR-pct | Avg EMA50 slope (ATR) |
|---|---|---|---|---|---|---|---|---|---|
| Quiet Trend | 293 | 22.9% | 1.89 | $234 | 2.48R | 3.88R | 33.0 | 0.37 | -0.23 |
| Strong Trend | 659 | 18.4% | 1.22 | $59 | 2.73R | 3.04R | 35.4 | 0.70 | +0.04 |
| Quiet Range | 518 | 17.2% | 1.29 | $85 | 2.75R | 3.30R | 18.9 | 0.35 | 0.00 |
| Volatile Range | 594 | 20.9% | 1.55 | $144 | 2.92R | 3.55R | 19.6 | 0.65 | +0.01 |

(293 + 659 + 518 + 594 = 2,064, matching the full trade count exactly —
every trade lands in exactly one bucket.)

## Where the edge concentrates, and where it doesn't

**Quiet Trend is the best regime by every metric that matters**: highest
profit factor (1.89), highest win rate (22.9%), highest expectancy per
trade ($234). It is also the smallest regime by trade count (293, 14% of
all trades) — the strategy's best conditions are comparatively rare.

**Strong Trend is the weakest regime**, with the lowest profit factor
(1.22) and the lowest win rate (18.4%) of the four, despite being the
*largest* regime by trade count (659, 32% of all trades) — nearly a third
of all trades happen in the regime that performs worst. ADX is actually
*higher* on average in Strong Trend (35.4) than in Quiet Trend (33.0); the
distinguishing variable between the two best/worst regimes is volatility
(ATR percentile 0.70 vs. 0.37), not trend strength. In other words: **this
strategy's edge degrades specifically when a strong trend coincides with
elevated volatility**, not when a strong trend is calm.

The two "Range" regimes (ADX < 25) sit in between, with Volatile Range
(PF 1.55) notably outperforming Quiet Range (PF 1.29) — the opposite
relationship to what holds inside the trending regimes. Volatility alone
does not have a consistent sign on its own; its effect depends on whether
ADX says the market is trending.

Average MAE-in-R is fairly flat across all four regimes (2.48R-2.92R) —
trades dig a broadly similar hole against them on average regardless of
regime, which is some evidence that the *stop placement* (a flat 0.5×ATR)
is not the thing driving the regime-level PF differences; the differences
are concentrated on the winning side (avg MFE ranges 3.04R-3.88R,
correlating with the PF ranking above almost exactly).

## Which regime contains the most losses

**Strong Trend contains the most total losing dollars** ($179,519 in gross
losses across the full backtest, tight-ECN costs), ahead of Volatile Range
($156,429), Quiet Range ($149,370), and Quiet Trend ($77,161) — consistent
with Strong Trend being both the largest regime by trade count and the
weakest by win rate and PF. It is the regime most worth scrutinizing if the
goal were ever to filter or otherwise modify the strategy (not done here,
per "do not optimize").

## Methodology notes

- Regime values are looked up from the signal bar via a one-bar `shift()`
  merge against `entry_time`, the same no-lookahead alignment `audit.py`
  uses for `atr_pct_entry`/`trend_state`.
- `loss_dollars` is a plain sum of negative-pnl trades within each regime
  bucket at the real, single historical dollar scale (not rebased) — valid
  because the four regimes are mutually exclusive partitions of the same
  one chronological trade sequence, unlike a by-year or by-session slice
  where dollar figures from different points in the equity curve would not
  be comparable without reconstruction (see `SESSION_ANALYSIS.md`'s
  methodology note for where that distinction mattered).
