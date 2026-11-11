# CLAUDE.md

- Product: event study and historical base rates for market-moving events. Read `PROJECT_STATE.md` (method rules) and `ROADMAP.md` (current sprint = v1) first.
- Current sprint: one category (`mideast-conflict`) and one asset (Brent). Don't widen it without Kai's OK. Put new ideas in `ideas.md`.
- Python, standard library only. Live fetches run in GitHub Actions (`.github/workflows/`), with keys stored as repo secrets. Never print a URL that contains a key.
- Brent: `scripts/fetch_eia_brent.py` writes `data/prices/brent_daily.csv`. Study: `python scripts/event_study.py`.
- Every probability shown has n, a 95% CI and a range. No look-ahead.
- Tests: `python -m unittest discover -s tests`.
- The parked ledger code (`ledger.py`, `onboarding.py`, `prototype.py`, `desk.py`) stays and keeps its tests passing. Build no new features on it.
- Pushing to `main` in this repo: standing OK from Kai (2026-11-11). Every push must pass the tests first. Still ask before deleting data, force-pushing, deploying, publishing or using paid APIs.
- End each session by updating `NEXT.md`.
