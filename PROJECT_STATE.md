# Project state

Updated 2026-11-11. This replaces the earlier direction. The old state is in `docs/archive/PROJECT_STATE_ledger_2026-10.md`.

## What the product is

A personal market-intelligence tool. It collects events that can move markets (wars and conflicts, mergers and acquisitions, sanctions, central bank decisions) and finds similar events in the past. It then measures what prices did afterwards and reports a historical base rate. For example:

> In 18 comparable events, Brent rose within 20 days in 11 (61%, 95% CI 39-80%). Median +4.2%, range -6% to +14%.

It also lists the assets the event is likely to affect (Brent, an energy index, NOK) and gives each one its own figures.

Kai makes every decision. The tool gives no guarantees and places no trades. Base rates come with their sample size, interval and range, every time.

## Decision log

- 2026-11-11, Kai: the product is event study plus historical base rates, with probabilities. This overrides the earlier "no forecasts / no recommendations" rule for Kai's own use. The public portfolio demo is framed as "historical base rates", not as investment advice to others.
- 2026-11-11: the personal ledger, valuation and performance work (`cursor/hm-01`, ONBOARD/VALUE/PRICE/NOTE slices) is parked. It is not deleted. The ingest code (`src/huginn_muninn/ingest/`: allowlisted client, cache, Norges Bank, ECB, SSB) is reused.
- Quotes and heuristics from well-known investors are shown as labeled commentary next to the numbers. They are never an input to a probability.

## Method rules (non-negotiable)

1. **No look-ahead.** Each event records its source and the date it became public. Default entry is `after_news`: the first close on or after that date (the earliest price you could act on), at most 5 days later. `before_news` (last close before the date) is an option for measuring the full reaction, and is labeled as such. Decided 2026-11-11.
2. **Always show n, the confidence interval and the range,** for events and baseline alike. No bare percentages. Below n = 8, show "too few" and no percentage. The code rejects any `min_n` below 8.
3. **Baseline.** Report the move after the event against the unconditional move over non-overlapping windows of the same length, so "oil usually rises" doesn't read as an event effect. Non-overlapping windows keep the baseline interval honest.
4. **Era split.** Results can be filtered by era (for example pre-2000, 2000-2014, 2015 onward). A regime change is shown, not hidden.
5. **Calibration.** Before any probability is trusted, backtest it: did the 60% calls come true about 60% of the time?
6. Decimal arithmetic or numpy float64 is fine for statistics. Prices stay as stored, with their source.

## Status

- Working: allowlisted ingest client and cache (stdlib), 196 tests, the parked ledger prototype.
- Done: event-study engine `src/huginn_muninn/study.py` (24 tests, Codex-reviewed 2026-11-11, all 5 findings fixed).
- Not started: event catalog, Brent price series, CLI, results page.
