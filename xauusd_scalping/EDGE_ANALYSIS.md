# XAUUSD Edge Analysis — What Is Real, What Is Not

This document is the research record behind `strategy.py`. It exists because
the request was explicitly to find a *real* edge before building anything —
not to assume RSI or Bollinger Bands work just because they're popular. The
tool used throughout is `research.py`; every number below is reproducible by
running `python3 research.py` (and the small in-sample/out-of-sample split
script described at the bottom).

## 1. The core problem: win rate is not evidence of edge

The first thing tested was a deliberately information-free null baseline:
purely random entries (no indicator, no trend filter — just a 1% per-bar coin
flip), passed through the *same* session/volatility filters used everywhere
else, evaluated with a **triple-barrier** test (walk forward over the real
high/low path; whichever of the target or stop is touched first, wins; if
neither is touched within the holding window, settle at the close).

```
random tp=1.0 sl=1.0   | n=636  win=42.3%  PF=0.61  avg_net=-0.390 $/oz
random tp=0.5 sl=1.5   | n=636  win=69.0%  PF=0.55  avg_net=-0.350 $/oz
```

Random entries with a small target and a wide stop win **69% of the time**
and still lose money at a rate worse than the entries with a 50/50 target/stop
ratio. This is the single most important fact this project established: win
rate is mostly an artifact of how asymmetric the target and stop are, not
proof that the entry has any predictive value. Any later result quoting a
~65%+ win rate has to be judged against this baseline, not in isolation —
which is why every test below also reports profit factor and average expectancy
per trade, not win rate alone.

## 2. What was tried and ruled out

About a dozen entry designs were tested in-sample with the triple-barrier
harness before arriving at the final design. All of these were rejected
because they failed to clear the null baseline above — i.e. no PF edge, or a
forward-return diagnostic showing the trigger was uncorrelated/anti-correlated
with subsequent price movement:

- RSI midline-cross + EMA21/55 pullback continuation.
- Donchian micro-breakout momentum continuation.
- EMA21-reclaim bounce with a structural swing-low/high stop.
- EMA9/21 crossover with a chandelier trailing stop.
- Plain Bollinger-band fade *without* an H1 trend filter (fading any
  deviation, including against the macro trend).
- Bollinger-band fade *with* an RSI<25/>75 confirmation filter (the RSI
  filter selects for trend-continuation, which fights a mean-reversion fade).
- Momentum/breakout entries generally — see §4.

## 3. The one design with a real raw edge: RSI(2) mean-reversion, in trend

The surviving design: take a short-term oversold/overbought extreme (RSI(2),
Connors-style) **only when it agrees with the higher-timeframe trend** — buy
RSI(2) dips below 10 only when the H1 EMA50 is above the H1 EMA200 (uptrend),
sell RSI(2) spikes above 90 only in an H1 downtrend. This is the only family
tested whose raw expectancy (before any transaction cost) is *and stays*
positive:

```
RSI2<5  trend  net@0.00   | n=4012  win=62.2%  PF=1.13  avg_net=+0.110 $/oz
RSI2<10 trend  net@0.00   | n=7500  win=62.5%  PF=1.12  avg_net=+0.105 $/oz
```

Profit factor above 1.0 *with zero spread/slippage applied* is the bar for
"there is a real signal here" — it means the win/loss distribution itself is
favorable, independent of cost. Random entries (§1) never clear this bar no
matter how the target/stop geometry is tuned; this one does.

### 3a. Confirmed in both non-overlapping windows (not a fluke)

Splitting the RSI(2)<10-in-trend signal at the in-sample/out-of-sample
boundary used everywhere else in this project (2018-12-31), the raw edge
holds independently in **both** halves:

```
IS  2012-2018   net@0.00   | n=4885  win=63.0%  PF=1.14  avg_net=+0.109 $/oz
OOS 2019-2022   net@0.00   | n=2615  win=61.5%  PF=1.09  avg_net=+0.099 $/oz
```

A signal that only "works" in one arbitrarily-chosen half of the data is
almost certainly overfit. This one was never tuned against the OOS half and
still clears PF>1 there, which is the strongest evidence available that the
effect is real rather than a backtest artifact.

## 4. What does not work: momentum/breakout

Gold M15 does not trend-continue at this horizon. N-bar range breakouts
(aligned with the same H1 trend filter, given every favorable assumption)
have **negative expectancy even at zero transaction cost**:

```
10-bar breakout  net@0.00   | n=5633  win=33.4%  PF=0.96  avg_net=-0.041 $/oz
20-bar breakout  net@0.00   | n=4034  win=33.4%  PF=0.96  avg_net=-0.037 $/oz
```

If the raw, cost-free PF can't clear 1.0, no amount of cost optimization,
filtering, or exit-rule tuning can rescue it — there's no edge to begin with.
This rules out the entire momentum/breakout family for gold M15, at least
with a pure technical trigger.

## 5. Cost sensitivity: the edge is real but thin

The RSI(2)-in-trend signal's raw PF (1.12-1.14) is well above the null
baseline, but it is a *small* edge in absolute terms (~$0.10/oz average, before
cost, per signal). Re-running the same signal/geometry test with spread and
slippage applied shows it erodes quickly:

```
RSI2<10 trend  net@0.00   | win=62.5%  PF=1.12  avg_net=+0.105 $/oz
RSI2<10 trend  net@0.10   | win=60.9%  PF=0.99  avg_net=-0.008 $/oz
RSI2<10 trend  net@0.35   | win=57.0%  PF=0.75  avg_net=-0.273 $/oz
```

Breakeven for this exact signal/target/stop geometry is **≈$0.09–0.10/oz**
round-turn cost. That is tight-ECN territory, not a standard retail fixed
spread (commonly $0.30–0.45/oz on gold). This single number is the reason the
rest of this project's design effort (the `first_green` scratch exit in
`backtest.py`) went into squeezing more out of the exit side, rather than
assuming the entry alone was good enough to trade as-is.

## 6. From signal to system: the `first_green` exit changes the breakeven math

§3-5 above score the entry+fixed-target geometry treating every signal as an
independent sample (no one-trade-at-a-time constraint, which is what
`research.py`'s `triple_barrier()` is for — it isolates signal quality from
position-management effects). `strategy.py` + `backtest.py` implement the
actual tradable system: one position at a time, with the **first_green** exit
(close the trade at the first bar after entry that closes in profit, rather
than waiting for a fixed target). This materially changes the realized win
rate and the cost breakeven — see `RESULTS.md` for the full backtest, but in
short: it lifts win rate to ~65-67% and moves the breakeven spread for the
*full system* (not just the entry) to roughly $0.10-0.17/oz, which is what the
final recommended cost assumption (`$0.10` ECN spread) is built around.

## 7. The exit rule is a separate decision from the edge itself

Everything above (§1-6) is about the **entry signal** — it is the only place
a real, cost-independent edge was found, and that finding does not change
based on what exit rule is layered on top of it. The exit rule only decides
how that raw edge gets converted into win rate, return smoothness, and
drawdown. Two exits were backtested end-to-end on the *same* entry signal:
scratching at the first profitable close (`first_green`, ~65%+ win rate, PF
~1.06-1.07) versus a fixed 1.6×ATR target against a 1.0×ATR stop (`atr_tp`,
~40-45% win rate, PF ~1.08-1.10, materially better Sharpe and year-to-year
consistency). `atr_tp` is now the default in `strategy.py` — see `RESULTS.md`
for the full side-by-side comparison and the reasoning. Neither exit changes
the cost requirement from §5; both need the same tight/ECN-grade spread to be
net positive, because that requirement comes from the entry signal's raw
edge size, not from the exit.

## 9. Time-of-day as a second, independent edge component (corrected)

Everything above treats the entry signal as if it applies uniformly across
the trading day. It does not. This section originally reported a profit
factor of 1.60 in-sample / 1.51 out-of-sample for a 14:00-16:00 window with a
0.5x/4.0x ATR exit, found by an exhaustive scan of every
`(session_start_hour, session_end_hour)` pair ranked by `min(IS_PF, OOS_PF)`.
**That ranking criterion is a selection-bias flaw**: sorting thousands of
candidates by how well they score on the out-of-sample window, and keeping
the one that scores best there, uses the out-of-sample data to choose the
model — it stops being out-of-sample the moment it's used that way, even
though no single candidate was ever "trained" on it in the conventional
sense. This section has been rewritten with a methodology that cannot leak
the same way.

### The honest version: train → validate → test, test touched once

1. **Train** (2012-05-15 → 2016-12-31) only: an exhaustive grid over every
   session window with at least 150 signals (275 windows) crossed with stop
   multiples 0.5-1.0x and target multiples 1.6-5.0x (reward:risk ≥ 1.5:1),
   13,152 valid candidates. (`generate_signals()` doesn't depend on the
   stop/target parameters, so it was computed once per session window and
   reused across all 48 exit ratios for that window — this cut the slow part
   of the grid from ~13,000 calls to 275 and made the full search tractable
   in ~19 minutes instead of being impractically slow.)
2. Candidates were filtered to `train_n ≥ 500` before ranking (11,656 of
   13,152 qualify) — this excludes narrow 1-hour windows that top the raw
   train-PF ranking on too few trades to trust.
3. The top 15 candidates by train profit factor were each checked, once,
   against **validate** (2017-2018), a window the train-only search never
   saw. All 15 of 15 generalized with validate PF > 1.0 (range ≈1.23-1.53,
   versus train PF range ≈1.84-1.90) — strong evidence the underlying
   time-of-day effect is real, since pure noise would not be expected to
   generalize this consistently across an independent window.
4. The single best candidate by validate PF — **session 13:00-16:00, stop
   0.5×ATR, target 4.5×ATR** — was locked in before any further data was
   examined.
5. The locked candidate was then evaluated against **test** (2019-2022),
   touched exactly once:

```
train    2012-16   sl=0.5 tp=4.5  | PF=1.86  n=963   win=21.7%  sharpe=2.37
validate 2017-18   sl=0.5 tp=4.5  | PF=1.53  n=384   win=20.1%  sharpe=1.91
test     2019-22   sl=0.5 tp=4.5  | PF=1.30  n=714   win=16.1%  sharpe=1.05
```

Profit factor declines monotonically from train to validate to test — the
pattern an honest, non-leaky search should produce, since some fitting to
the train window is unavoidable. What matters is that validate and test both
stay comfortably above 1.0, not that they match train. The mechanism
hypothesis from the original pass is unchanged and still plausible: this
window overlaps major US economic data releases and the New York cash
equity open, both of which tend to produce sharp, fast-reverting volatility
spikes in gold — the kind of move a short-term mean-reversion entry is built
to catch.

A few sanity checks on the locked configuration, full-period:

- **Not outlier-driven**: the 5 largest winning trades are 4.0% of total
  gross profit ($32,113 of $799,265) — up slightly from the 2.3% reported
  for the original (leaky) config, but still far from "a few lucky trades
  explain the result."
- **Exit-reason mix is clean**: of 2,064 full-period trades, 1,662 exit via
  `stop_loss`, 271 via `take_profit`, and 131 via `time_stop` — no sign of
  degenerate behavior from the wide target or narrow session.
- **Losing streaks are real and longer than originally reported**: the worst
  run in the full-period backtest is **32 consecutive losing trades**, up
  from the 23 reported for the original, leaky-selected config. Statistically
  unsurprising at a ~20% win rate, but a genuinely worse number that the
  original document understated.

### What this changes versus the original (leaky) claim

The honest, locked configuration's full-period profit factor is **1.41**
(tight-ECN spread) / **1.10** (retail spread) — both real and positive, but
lower than the originally-claimed 1.53 / 1.13. The more consequential change
is at retail spread, out-of-sample only: the original version claimed this
was "roughly breakeven" (PF 0.99); the honest redo shows it is **negative**
(PF 0.91, −18.3% return over 2019-2022). See `RESULTS.md` for the full
backtest-results table, the train/validate/test cascade in context, and the
complete honest conclusion.

## 10. Honest summary

- **Real edge exists**: RSI(2) mean-reversion, taken only in the direction of
  the H1 macro trend, has genuine positive raw expectancy (PF ≈ 1.09-1.14),
  confirmed independently in two non-overlapping multi-year windows.
- **No edge found** in momentum/breakout continuation on gold M15 at any cost
  level — this family was conclusively ruled out, not just deprioritized.
- **Win rate alone is not the goal** — it is a side effect of exit-rule
  choice (the `first_green` scratch exit), and a high win rate without a
  positive raw signal underneath it (§1) is worthless.
- **The edge is thin at the entry-signal level**: it requires sub-$0.10-0.17/oz
  round-turn execution cost to be net positive when harvested with a
  symmetric or near-symmetric exit. This is a real constraint on how/where
  this strategy can be automated, not a cosmetic detail.
- **A selection-bias flaw was found and fixed in this project's own process**
  (§9): an earlier pass picked its session window by a criterion
  (`min(IS_PF, OOS_PF)`) that used the out-of-sample window to choose among
  thousands of candidates, which is itself a form of overfitting. The
  redone search uses a leak-proof train (2012-16) → validate (2017-18) →
  test (2019-22, touched once) cascade.
- **Time-of-day still concentrates the edge, honestly confirmed**: the same
  RSI(2)-in-trend signal is materially stronger in a 13:00-16:00
  platform-time window than across the full session, with profit factor
  declining monotonically and plausibly from train (1.86) to validate (1.53)
  to a never-touched test set (1.30). Combined with a wider 9:1 reward:risk
  exit, full-period profit factor reaches **1.41 (ECN) / 1.10 (retail)** —
  real, but lower than the original (leaky) claim of 1.53-1.60.
- **A genuinely new, sobering finding**: out-of-sample performance at a
  standard retail spread is **negative** (PF 0.91, −18.3%), not "roughly
  breakeven" as the original analysis claimed. A tight, ECN-grade spread is
  closer to a requirement than a nice-to-have for this strategy going
  forward.
- **The win-rate/frequency trade-off is also worse than originally stated**:
  win rate (~19-21%) and trade frequency (~150-200/year) are similar to
  before, but the worst losing streak in the full-period backtest is 32
  consecutive losses, up from the originally-reported 23. See `RESULTS.md`
  for the full cost-sensitivity table, the win-rate trade-off, and the
  live-trading implications.

## Reproducing this analysis

```bash
cd xauusd_scalping
python3 research.py   # null baseline, the edge (RSI2-in-trend), and the
                       # momentum/breakout ruled-out test, at $0.00/$0.10/$0.35
```

The in-sample/out-of-sample split in §3a is not part of `main()` (it would
duplicate the same call pattern three times); reproduce it by calling
`build_features`, `triple_barrier`, and `summarize_signal` from `research.py`
directly with a date mask, as shown in the snippet in §3a.
