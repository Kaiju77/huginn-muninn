# Review request for Codex, round 4 (2026-11-11)

Rounds 1-3 are logged in `REVIEW.md`. Review everything after `dd45fd1`:

- `src/huginn_muninn/daily.py`, `scripts/daily_report.py`, `scripts/fetch_news.py`, `tests/test_daily_report.py`
- The new steps in `.github/workflows/fetch-prices.yml` (news, brief, commit)
- `reports/latest.md`

Run:

    python -m unittest tests.test_daily_report -v
    python scripts/daily_report.py --today 2026-03-20
    python scripts/daily_report.py

Check, and report each finding with file:line, severity and a failing example:

- **Look-ahead.** For a past `--today`, does anything use data after that date: prices, events, the comparables used for base rates, news?
- **Unusualness rank.** `daily.move` ranks today's absolute 1-day move against earlier days. Is the rank correct (ties, today excluded from its own history, non-positive WTI closes)?
- **Event context.** Comparables exclude the event's own episode and later events. Is "trading days since" correct for weekend events?
- **Wording.** Does anything in the brief imply a cause or a forecast? Does every share have n, CI, range and baseline?
- **GDELT.** Query, parsing, failure handling. Can a failure produce a misleading brief?
- **Workflow.** Can the brief or the news commit hide a price-fetch failure, or commit partial data?

Report only. Don't edit files.
