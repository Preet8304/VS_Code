# Session Breakdown of Existing Trades

Read-only research, produced by `session_analysis.py`. Trades come from
`audit.run_audit()` unchanged. Each trade's entry hour (platform time, see
`data_loader.py`'s documented caveat that this is broker/vendor time, not
strict UTC) is classified into the four conventional forex session windows
requested:

| Session | Platform hours |
|---|---|
| Asian | 00:00–08:00 |
| London | 08:00–13:00 |
| London+NY overlap | 13:00–17:00 |
| New York | 17:00–22:00 |

These are the standard textbook session boundaries, applied directly — not
fitted, not searched.

## The result is trivial, and that itself is the finding

**100% of all 2,064 trades (2,064/2,064) fall in the London+NY overlap
bucket.** Asian, London-only, and New-York-only all show exactly zero
trades.

| Session | Trades | Win rate | Profit factor | Avg R | Max drawdown |
|---|---|---|---|---|---|
| Asian | 0 | — | — | — | — |
| London | 0 | — | — | — | — |
| **London+NY overlap** | **2,064** | **19.4%** | **1.42** | **0.537R** | **-13.9%** |
| New York | 0 | — | — | — | — |

This is mechanical, not a surprise: the strategy's own locked session
filter (`session_start_hour=13, session_end_hour=16`) only ever allows
entries in platform hours 13:00-15:59 — a strict subset of the 13:00-17:00
overlap window above. No entry can ever occur outside it. This is the same
"session-bucket triviality" the original trade-by-trade audit already
flagged using a different (asian/london/ny/late_ny) bucketing convention —
it reproduces here under the standard four-session convention too, for the
same underlying reason.

**One session contains literally all of the edge, by construction** — the
strategy was already deliberately narrowed to this window (see
`EDGE_ANALYSIS.md` §9-§10 for how and why), so this result confirms that
choice rather than discovering anything new about session structure.

## By year (within the one populated bucket)

| Year | Trades | Win rate | Profit factor | Avg R | Max drawdown* |
|---|---|---|---|---|---|
| 2012 | 160 | 19.4% | 1.68 | 0.620R | -5.9% |
| 2013 | 226 | 19.5% | 1.52 | 0.473R | -6.1% |
| 2014 | 206 | 23.8% | 1.95 | 0.822R | -6.8% |
| 2015 | 189 | 23.8% | 2.16 | 0.945R | -7.3% |
| 2016 | 182 | 22.0% | 1.78 | 0.730R | -5.5% |
| 2017 | 166 | 27.7% | 2.56 | 1.333R | -5.7% |
| 2018 | 219 | 14.2% | 1.01 | 0.022R | -13.9% |
| 2019 | 255 | 16.1% | 1.10 | 0.108R | -9.5% |
| 2020 | 194 | 16.0% | 1.34 | 0.326R | -6.8% |
| 2021 | 233 | 16.3% | 1.40 | 0.390R | -7.7% |
| 2022* | 34 | 14.7% | 1.40 | 0.385R | -2.6% |

\* 2022 is a partial year (data ends 2022-03-04); per-year max drawdown is
reconstructed from each year's own R-multiples compounding a fresh $10,000
base (see methodology note below) — it answers "what would the drawdown
have looked like if you'd only ever traded this one year," not a slice of
the real multi-year equity curve.

**2018 stands out as the weakest year** by a wide margin: PF barely above
breakeven (1.01) and the deepest single-year drawdown (-13.9%) of the
eleven years shown. 2017 is the strongest (PF 2.56). This matches the
already-documented full-period yearly pattern in `RESULTS.md` — nothing new
here beyond confirming the by-session breakdown is, in this case, identical
to the by-year breakdown of the whole strategy, since there is only one
session.

## Methodology note: why per-year drawdown needed a fix mid-analysis

An initial version of this breakdown computed each year's max drawdown by
summing that year's raw dollar `pnl` against a freshly reset $10,000
baseline. That produced nonsensical figures (drawdowns as deep as -148%, a
mathematical impossibility for a percentage drawdown) because those dollar
`pnl` values were generated using the *real*, much-larger compounded equity
that existed by 2018-2021 in the single full historical run — summing
large-equity-era dollars against a artificially small reset baseline
overstates drawdown enormously. The fix: reconstruct a fresh compounding
equity curve from each year's own sequence of **R-multiples**
(`equity *= 1 + r×risk_per_trade`, the same relation the real engine uses
internally) rather than reusing the dollar figures directly. This is
mathematically exact for the single full chronological sequence (it
reproduces the official -13.9% full-period max drawdown exactly) and is the
only valid way to ask "what if you'd only traded this slice" for any
sub-period that isn't the complete sequence from the very first trade.
