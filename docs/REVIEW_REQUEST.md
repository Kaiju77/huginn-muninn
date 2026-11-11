# Review request for Codex, round 5 (2026-11-11)

Rounds 1-4 are logged in `REVIEW.md`. Review the latest commit:

- Round 4 fixes: `scripts/daily_report.py` (`news_lines`, quiet-day fallback) and `scripts/fetch_news.py` (`parse`)
- New: `src/huginn_muninn/candidates.py`, `scripts/suggest_events.py`, `scripts/approve_event.py`, `.github/workflows/approve-event.yml`, the new steps in `fetch-prices.yml`, `tests/test_candidates.py`

Run:

    python -m unittest tests.test_candidates tests.test_daily_report -v

Check, and report each finding with file:line, severity and a failing example:

- **Round 4 fixes.** Are all four really closed? Any remaining path where old or future headlines appear as today's?
- **Screening rule.** False positives and negatives in `ESCALATION` and `REGIONS` (word boundaries, words like "war" in "award", "mine" in "determine"). Give concrete headline examples.
- **Approval safety.** Can `approve_event.py` corrupt the catalog, approve twice, or create a duplicate `event_id` (two candidates for one region and day)? Is the workflow input handled safely (shell injection through `title` or `episode`)?
- **Headline filter.** `daily.relevant` keeps titles with an energy word or a monitored region. False positives and negatives with real examples (for example "gas" in "gaslighting", or "Nine Energy" earnings).
- **AI screen** (`src/huginn_muninn/ai_screen.py`, `scripts/ai_screen.py`, `tests/test_ai_screen.py`). Can model output get past validation in a harmful way, for example prompt injection through headlines, a wrong region, or cited numbers that don't exist? Is the fallback to the keyword screen correct? Is the token ever logged?
- **Look-ahead.** Can an approved event leak into base rates for dates before it?
- **Workflow.** Concurrency between `approve-event` and `fetch-prices`; what's committed; failure modes.

Report only. Don't edit files.
