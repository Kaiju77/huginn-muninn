# Roadmap

Updated 2026-11-11. The old ledger roadmap is in `docs/archive/ROADMAP_ledger_2026-10.md`.

## v1: one category, one asset (done 2026-11-11, extended to four assets)

Done means: `python scripts/event_study.py --category mideast-conflict --asset brent` prints a base-rate summary, and a Streamlit page shows the same summary with a chart of every event's path.

1. **Event catalog.** `data/events/mideast-conflict.csv` with 20-30 hand-curated events. Columns: `event_id, date_public, title, category, region, source_url, notes`.
2. **Price series.** Daily Brent spot from EIA open data (series `PET.RBRTE.D`, needs a free API key), cached through the existing ingest client. Add `api.eia.gov` to the allowlist.
3. **Event-study engine.** `src/huginn_muninn/study.py`. For windows of +5, +20 and +60 trading days: share of events with a rise, Wilson 95% CI, median, min/max, and the unconditional baseline. Pure functions, unit-tested on synthetic series with known answers.
4. **Results page.** Streamlit with one table and one chart. Local first.

## v2: more events, more assets

- Categories: M&A announcements (for the acquirer and target share prices), sanctions, central bank surprises.
- Map each event to the assets it affects (category -> asset list), with separate figures per asset: Brent, OSEBX energy, Equinor, NOK/USD.
- Calibration backtest report.

## v3: live intake

- Daily news and filings intake. Claude classifies a new event into a catalog category and finds its nearest past matches. Every claim links to its source.
- Daily brief page that runs on a schedule (GitHub Actions), published publicly. This is the v1.0 for the portfolio.

## Out of scope until v3 ships

Trade execution, broker connections, portfolio optimization, paid data vendors, and scraping that isn't allowed.
