# Review request for Codex, round 3 (2026-11-11)

Rounds 1 and 2 are logged in `REVIEW.md`. Review everything after `1fabf81`:

1. `c1686c4`: `src/huginn_muninn/assets.py`, `scripts/fetch_prices.py` (EIA Brent, WTI, Henry Hub; Norges Bank USD/NOK), `scripts/event_study.py`, `study.event_path`, `.github/workflows/fetch-prices.yml`, `tests/test_prices_pipeline.py`.
2. `72f63c1` and later: `src/huginn_muninn/report.py`, `app/streamlit_app.py`, `tests/test_report_and_app.py`.
3. Real data in `data/prices/*.csv`, once the workflow has committed it.

Run (the read-only sandbox can't create temp dirs, so some tests may error there; say which):

    python -m unittest tests.test_study tests.test_catalog tests.test_prices_pipeline tests.test_report_and_app -v
    python scripts/event_study.py
    python scripts/event_study.py --entry before_news

Check, and report each finding with file:line, severity and a failing example:

- **WTI negative price.** `allow_nonpositive` is on for WTI only. Does anything downstream (study, baseline, paths, page) mishandle the -36.98 print on 2020-04-20?
- **Norges Bank.** `fetch_norges` reuses `ingest/norges.parse_exr`. Is the parse correct for the full history? Units: NOK per 1 USD.
- **Henry Hub.** Is EIA route `natural-gas/pri/fut`, series `RNGWHHD` the Henry Hub daily spot? If not, say what is.
- **Workflow.** With `continue-on-error`, can a partly failed run commit bad data? Is the final failure step right? Is the rebase-before-push safe?
- **Page.** Does anything on the page show a share without n and CI, or a misleading label? Is the chart's MEDIAN line computed correctly when paths have different lengths?
- **Event paths.** `event_path` against `event_return` for both entry rules: same entry index?
- **Price data.** Spot-check each CSV for gaps, duplicates and outliers.

Report only. Don't edit files.
