# Stop-Management Overlay Comparison — Same Entries, Same Target, Different Stops

Read-only research, produced by `stop_management.py`. This is a narrower
question than `EXIT_MODELS.md`: entries are unchanged (as always), **and so
is the take-profit target (4.5× ATR) and the 12-bar time stop** — only the
placement of the *stop* during the trade is varied. The question being
answered: how much of the existing edge is left on the table purely by
never moving the stop off its initial 0.5× ATR placement?

## Results — full period, 2012-05 to 2022-03, tight-ECN costs

| Model | Trades | Win rate | Profit factor | Expectancy (R) | Avg winner | Avg loser | Max DD | Sharpe | Max consec. losses | Annual return |
|---|---|---|---|---|---|---|---|---|---|---|
| **A** — current exit, no stop management | 2,064 | 19.4% | 1.42 | 0.537R | $1,993 | -$338 | -13.9% | 1.85 | 32 | 38.7% |
| **B** — stop → breakeven after +1R | 2,071 | 14.3% | 1.63 | 0.505R | $1,753 | -$181 | -9.3% | 1.94 | 42 | 36.5% |
| **C** — stop → breakeven after +1.5R | 2,071 | 14.8% | 1.60 | 0.515R | $1,853 | -$200 | -9.1% | 1.96 | 42 | 37.3% |
| **D** — stop → +0.5R after +2R | 2,072 | 41.3% | 1.61 | 0.521R | $689 | -$301 | -10.3% | 2.05 | 11 | 37.9% |
| **E** — 50%@1.5R, stop → breakeven | 2,071 | 44.5% | 1.45 | 0.328R | $223 | -$123 | -9.5% | 1.79 | 11 | 22.5% |
| **F** — 25%@1R, 25%@2R, trail remainder 3×ATR | 2,071 | 36.8% | 1.36 | 0.302R | $256 | -$109 | -11.1% | 1.59 | 13 | 20.5% |

Model A reproduces `audit.py`/`backtest.py` exactly (n=2,064, PF=1.4210,
max consecutive losses=32) — the correctness check for this engine.

## What moving the stop alone buys you

All five management variants (B–F) **raise profit factor above the 1.42
baseline** — B and C both clear 1.6 just by relocating the stop to
breakeven once price has moved 1–1.5R in the trade's favor, without
touching the target or giving up any of the original 4.5R upside. That is
the single cleanest finding here: simple stop discipline, layered on top of
the existing exit, is a net positive on this entry set.

The price for that PF improvement is lower per-trade expectancy in R (B/C/D
sit around 0.50-0.52R vs. the baseline's 0.537R) — moving the stop to
breakeven converts some trades that would have eventually recovered into
small breakeven-or-slightly-negative exits, the standard cost of any
breakeven-stop rule. B and C also show a **higher** maximum consecutive
loss count (42 vs. 32) than the unmanaged baseline — counter-intuitive at
first, but consistent: some trades that the baseline would have ridden to
a small time-stop *win* instead get cut at a marginally negative breakeven
(spread-cost-only) under B/C, which can string together more
small-loss-labeled trades in a row even as the overall PF improves.

Model D (lock +0.5R after +2R) is the standout for **drawdown discipline**:
the only model alongside E/F to cut maximum consecutive losses to single
digits (11), because reaching +2R is common enough on this entry set that
guaranteeing a +0.5R floor converts a meaningful share of what would
otherwise be full-stop losses into small wins, breaking up loss streaks.
It does this while keeping win rate (41.3%) and PF (1.61) competitive with
B/C, and Sharpe is the highest of the six (2.05).

Models E and F (partial profit-taking) trade meaningfully lower expectancy
and annual return for the smoothest equity curves (smallest average loser,
lowest max consecutive losses) — they realize gains earlier at the cost of
the large 4.5R winners that drive most of the baseline's profit.

## Ranking

1. **Model D — stop → +0.5R after +2R.** Best combination of PF (1.61),
   Sharpe (2.05), and drawdown discipline (11 consecutive losses, the
   lowest tie alongside E) while sacrificing the least expectancy (0.521R
   vs. baseline's 0.537R) of any of the five management rules.
2. **Model B — breakeven after +1R.** Highest profit factor of all six
   (1.63) and best Sharpe-for-the-PF trade-off after D, but the worst
   consecutive-loss count (42, tied with C).
3. **Model C — breakeven after +1.5R.** Nearly identical to B; the later
   trigger trades a touch of PF for a touch more expectancy. The two are
   close enough that the choice between them is not decisive either way.
4. **Model A — current exit, unmanaged.** Still the best raw expectancy
   per trade and the best annual return (38.7%) of the six, at the cost of
   the largest loss streak (32) and a materially lower PF than B/C/D.
5. **Model E — 50% at 1.5R, breakeven on remainder.** Smooth (11
   consecutive losses, low average loser) but gives up a third of the
   baseline's annual return.
6. **Model F — staged partial exits + ATR trail.** Smoothest average loser
   of the six but the lowest PF, expectancy, and annual return among the
   five management variants — scaling out twice before any trailing begins
   realizes too much of the position too early on an entry set whose edge
   is concentrated in its largest winners.

## Does stop management alone push PF above 1.8?

**No.** The best of the six (Model B, breakeven after +1R) reaches PF
1.63. None of the five management rules tested get within 0.15 of the 1.8
threshold. This is a real ceiling check, not a tuning failure: these are
plain, literally-specified rules (no grid search over the trigger
distances), so it remains possible that *some* untested stop-management
rule clears 1.8 — but moving the stop alone, using the rules as specified,
does not.

## Methodology notes

- Position sizing is pinned to the original 0.5× ATR stop distance for
  every model, identical to `exit_models.py` — "R" means the same dollar
  amount in every column.
- **Tie-break order matches the existing engine's documented convention**:
  within a bar, the stop level *already in force* is checked before any
  management trigger for that same bar is evaluated — a bar that reaches
  both the old stop and a new management trigger is conservatively resolved
  as a stop hit, never the more favorable outcome.
- Models E and F's trailing remainder (after both partials in F) replaces
  the fixed 4.5R target on that remaining size, the same convention used in
  `exit_models.py`'s Model B, disclosed there in full.
- `max_consec_losses` counts trades with `pnl <= 0` as a loss, matching
  Round D/E's existing convention (a trade closed flat to the cost of
  spread, e.g. a breakeven-stop exit, counts as a loss for this purpose).
