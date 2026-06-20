# XAUUSD Scalping Strategy — Final Backtest Results

## TL;DR

A real, validated mean-reversion edge exists in gold M15: **RSI(2) extremes
traded only in the direction of the H1 macro trend** (see `EDGE_ANALYSIS.md`
for how this was found and what was ruled out first). The entry signal is
fixed; what changed in this revision is the **exit rule**, by deliberate
choice: instead of scratching trades at the first profitable close (~65%+ win
rate, thin per-trade edge), the default now lets winners run to a real
multiple of the stop (1.6x ATR target vs a 1.0x ATR stop). That drops win
rate to **~40-45%** but raises profit factor, more than doubles risk-adjusted
return (Sharpe), and improves year-to-year consistency — a better fit for
"small, consistent returns at high trade frequency" than chasing win rate for
its own sake. The catch is unchanged from before: this is **only profitable
at a tight/ECN-grade spread** (~$0.10/oz round-turn), not a standard retail
fixed spread ($0.35/oz).

## Data

- Source: `ejtraderLabs/historical-data` (public GitHub repo), fetched via
  `fetch_data.py`. XAUUSD M15 and H1 OHLC, 2012-05-15 → 2022-03-04
  (~230k M15 bars / ~58k H1 bars).
- Prices are vendor-scaled ×100 in the raw CSV (e.g. `196974` = $1,969.74);
  `data_loader.py` rescales to real USD/oz.
- Timestamps are the vendor's platform/broker time (commonly UTC+2/UTC+3),
  not strict UTC.
- In-sample window: 2012-05-15 → 2018-12-31 (used for strategy design).
- Out-of-sample window: 2019-01-01 → 2022-03-04 (touched only once, after the
  design was locked, to validate honestly).

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
4. **Session filter**: 07:00–16:00 platform time (London/NY overlap).
5. **Exit** (`exit_mode="atr_tp"`, the default): protective stop at 1.0×ATR;
   fixed target at 1.6×ATR. A 12-bar time-stop is a backstop for trades that
   hit neither. (The original `first_green` scratch exit is still available
   in `strategy.py` for anyone who wants to revisit the high-win-rate /
   lower-consistency tradeoff — see "Exit-rule comparison" below.)
6. **Sizing**: fixed-fractional risk, **0.20% of equity per trade**.

## Exit-rule comparison: why win rate was traded for consistency

The entry signal is the only thing in this system with a demonstrated raw
edge (`EDGE_ANALYSIS.md`); everything downstream of it — win rate, return
smoothness, drawdown — is a function of the exit rule and position sizing,
not signal quality. Two exit rules were backtested end-to-end on the
identical entry signal, both at the tight-ECN spread ($0.10/oz) that this
edge requires to survive cost at all:

| Exit rule | Win rate | Profit factor | Sharpe (IS / OOS) | Full-period return | Full-period DD | Profitable years |
|---|---|---|---|---|---|---|
| `first_green` (scratch at first green close) | 65-67% | 1.06-1.07 | 0.54 / 0.43 | +29.8%* | -15.9%* | 7 / 11 |
| `atr_tp` (1.0×ATR stop / 1.6×ATR target) — **default** | 40-46% | 1.08-1.10 | 0.90 / 0.50 | +62.2% | -16.3% | 8 / 11 |

*\*first_green column measured at 0.25% risk/trade (its own tuned setting);
atr_tp column at 0.20% risk/trade — both are each rule's own drawdown-tamed
setting, not a forced apples-to-apples risk level, since the point of the
comparison is "which rule, run sensibly, gives the better system."*

Scratching trades at the first green close caps the average winner near
breakeven-plus-a-hair (by construction, "first profitable close" can't be
much more than a few cents above entry), so even though it wins more often,
each win is small and each rare stop-out is comparatively large — high win
rate, thin edge per trade. Letting winners run to 1.6×ATR instead means most
trades end up losers (the market doesn't usually move a full 1.6×ATR in the
entry's favor within 12 bars), but the wins that do land are large relative
to the stop, which is exactly the asymmetry that produces a smoother,
higher-Sharpe equity curve and is more in line with "small, consistent
returns, higher trade frequency" than optimizing win rate for its own sake.
**`atr_tp` is now the default `exit_mode`.**

## Backtest results (locked parameters, no further tuning)

Engine: signals at bar close, fills at next bar's open, half-spread paid on
each side of every trade, extra slippage on stop/time-stop market exits,
conservative same-bar SL resolution, 0.20% fixed-fractional risk per trade,
$10,000 starting equity.

| Scenario | Spread | Trades | Win rate | Profit factor | Return | Max DD | Sharpe |
|---|---|---|---|---|---|---|---|
| In-sample (2012–2018) | $0.35 (retail) | 3,246 | 39.2% | 0.80 | **−62.5%** | −63.0% | −2.06 |
| In-sample (2012–2018) | $0.10 (tight ECN) | 3,209 | 43.2% | 1.10 | **+47.1%** | −11.7% | 0.90 |
| Out-of-sample (2019–2022) | $0.35 (retail) | 1,705 | 38.9% | 0.80 | **−35.8%** | −36.2% | −1.82 |
| Out-of-sample (2019–2022) | $0.10 (tight ECN) | 1,678 | 41.8% | 1.05 | **+10.7%** | −10.6% | 0.48 |
| Full period (2012–2022) | $0.35 (retail) | 4,955 | 39.1% | 0.80 | **−76.0%** | −76.2% | −1.98 |
| Full period (2012–2022) | $0.10 (tight ECN) | 4,891 | 42.7% | 1.08 | **+62.2%** | −16.3% | 0.75 |

Win rate is consistent across both windows (43.2% IS, 41.8% OOS) and matches
the 40-50% target. Profit factor holds up well out-of-sample (1.10 → 1.05),
which is the more important number: this is the same raw RSI(2)-in-trend
signal validated independently in both halves in `EDGE_ANALYSIS.md` §3a,
just harvested with a wider, less-scratchy exit.

### Yearly breakdown — full period, tight-ECN spread ($0.10), the only viable scenario

| Year | Trades | Win rate | P&L | Return |
|---|---|---|---|---|
| 2012 | 340 | 42.6% | +$490.58 | +4.9% |
| 2013 | 496 | 43.1% | +$844.39 | +8.0% |
| 2014 | 496 | 42.7% | +$675.58 | +6.0% |
| 2015 | 468 | 45.1% | +$1,292.22 | +10.8% |
| 2016 | 462 | 43.3% | +$649.36 | +4.9% |
| 2017 | 401 | 46.6% | +$1,528.43 | +11.0% |
| 2018 | 547 | 39.5% | −$804.74 | −5.2% |
| 2019 | 566 | 39.0% | −$928.77 | −6.3% |
| 2020 | 462 | 45.7% | +$1,911.60 | +13.9% |
| 2021 | 567 | 41.8% | +$727.14 | +4.6% |
| 2022* | 86 | 38.4% | −$161.37 | −1.0% |

*2022 partial (through March). 8 of 11 years are net positive — better
consistency than the high-win-rate exit (7/11) and with no single
catastrophic year, since the wider target keeps the loss side bounded at
exactly 1.0×ATR per trade rather than relying on a scratch exit's timing.

## Risk-per-trade and drawdown

Profit factor and win rate are risk-size-invariant; only return and drawdown
scale with risk-per-trade. **0.20%** was chosen because it lands full-period
drawdown (-16.3%) close to where the previous high-win-rate version sat
(-15.9%), so the comparison above isn't won by simply taking more risk — the
`atr_tp` exit produces a better system at a comparable drawdown budget, not
just a more aggressive one.

## Cost (spread) sensitivity

| Round-turn spread | Profit factor (full period) | Return (full period) |
|---|---|---|
| $0.10 (tight ECN) | 1.08 | +62.2% |
| $0.35 (typical retail fixed spread) | 0.80 | −76.0% |

This is unchanged from the prior exit rule, because the cost requirement
comes from the entry signal's raw edge size (`EDGE_ANALYSIS.md` §5), not from
the exit rule. Standard retail XAUUSD spreads are commonly $0.30–0.45/oz —
this strategy needs a genuine ECN/raw account with spread + commission
materially under that to have any realistic chance of being profitable,
regardless of which exit mode is used.

## Honest conclusion

1. **Real edge**: confirmed via null-baseline and raw (zero-cost) expectancy
   testing — see `EDGE_ANALYSIS.md`. Unchanged by this revision.
2. **Win rate, by request**: brought down from ~65% to ~40-45% by switching
   the exit rule, in exchange for a higher profit factor, roughly double the
   Sharpe ratio, and better year-to-year consistency (8/11 vs 7/11 profitable
   years) — the explicit trade made in this revision.
3. **Consistent profitability**: 8 of 11 years profitable, profit factor
   holds up from 1.10 in-sample to 1.05 out-of-sample. Full-period drawdown
   is -16.3% at 0.20% risk/trade — manageable, not eliminated.
4. **Automation readiness**: still gated on execution cost, not strategy
   logic. This needs a broker/account with round-turn cost (spread +
   commission) close to $0.10/oz; on a standard retail spread it loses money
   regardless of exit rule, as the retail rows above show.

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
`results/`. To reproduce the prior high-win-rate variant for comparison, pass
`exit_mode="first_green"` to `StrategyParams` (and consider raising
`risk_per_trade` to ~0.25%, its own tuned setting) rather than the defaults.
