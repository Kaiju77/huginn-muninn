# Review request for Codex, round 2 (2026-11-11)

Branch `claude/event-study-plan`. Round 1 is logged in `REVIEW.md`. Review the commits after `06b5e03`:

1. `a45cb41`: `data/events/mideast-conflict.csv`, `data/events/README.md`, `src/huginn_muninn/catalog.py`, `tests/test_catalog.py`.
2. The latest commit: entry rules `after_news` (default) and `before_news` in `src/huginn_muninn/study.py`, with tests in `tests/test_study.py`.

Codex's read-only sandbox can't create temp dirs, so use:

    python -m unittest tests.test_study tests.test_catalog -v

Check, and report each finding with file:line, severity and a failing example:

- **Entry rules.** Is `after_news` really the first close on or after `date_public`, and `before_news` the last close strictly before? Is the `max_gap_days` check right at both ends of the history and across gaps?
- **Catalog data.** For each row: is `date_public` the date the news broke in Europe/US trading time? Is `episode` grouping sensible (do any two episodes really belong together, or one should be split)? Flag any date you believe is wrong, with your source.
- **Catalog loader.** Missing validation, CSV edge cases (quotes, BOM, trailing blank lines), and `first_per_episode` ordering.
- **Docs vs code.** `PROJECT_STATE.md` rule 1 and `data/events/README.md`.

Report only. Don't edit files.
