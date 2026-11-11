# CLAUDE.md

- Product here is the evidence-first personal finance system (see `docs/DIRECT_PROJECT_HANDOFF.md` on master and `ROADMAP.md`). Synthetic data only.
- Standard-library Python. No dependencies are installed. Decimal for all money.
- Tests: `python -m unittest discover -s tests`. End-to-end: `python scripts/e2e_portfolio.py` (`docs/E2E_PORTFOLIO.md`).
- Never push, merge, deploy, restart services, fetch EDGAR/FRED, or connect live financial sources without Kai's explicit OK.
- Work on branches. `master` holds uncommitted handoff edits; leave them alone.
- End each session by updating `NEXT.md`.
