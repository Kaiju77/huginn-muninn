# Review request for Codex (2026-11-11)

Branch: `claude/event-study-plan`. Base for comparison: `cursor/hm-01`.

Review three commits:
1. `adddad7`: `scripts/e2e_portfolio.py` and `tests/test_e2e_portfolio.py`, an end-to-end HTTP check of the parked ledger prototype.
2. `e091ea5`: product redefinition (`PROJECT_STATE.md`, `ROADMAP.md`, `CLAUDE.md`, `NEXT.md`, `ideas.md`).
3. The latest commit: `src/huginn_muninn/study.py` and `tests/test_study.py`, the event-study engine.

Run:

    python -m unittest discover -s tests
    python scripts/e2e_portfolio.py

Then check, and report each finding with file:line, severity and a failing example:

- **Look-ahead.** Can any result use a close dated after `date_public` as the entry? Is the weekend/holiday rule right?
- **Statistics.** Wilson interval correctness; rise defined as change > 0; the baseline uses overlapping windows (is that acceptable for a share and a median?); the `min_n` cut-off.
- **Era filter.** Events are selected by `date_public`, baseline windows by start date, and exits may fall after the era end. Is that consistent?
- **Edge cases.** Non-positive prices, unsorted or duplicate closes, horizon at the end of the history, empty event list.
- **Tests.** Does each test assert behavior that matters? Is anything important untested?
- **Docs vs code.** Do `PROJECT_STATE.md` method rules match what `study.py` actually does?

Don't modify files. Report only. Then write your findings to `REVIEW.md` under a dated heading, if Kai asks.
