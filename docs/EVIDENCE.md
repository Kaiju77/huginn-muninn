# Evidence

EVIDENCE-01 records source limits and ingests one recorded synthetic fixture. Independent review on 2026-10-11 approved that register. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120`. INGEST-01, described in `docs/INGEST.md`, later connects Norges Bank and the ECB for an explicit manual refresh. Independent review of INGEST-01 is not yet recorded. This note is not production financial readiness.

## EVIDENCE-01 kept live fetch off

Live API acquisition was not part of EVIDENCE-01. That increment did not call Norges Bank, Statistics Norway, FRED, the SEC, or the ECB. It does not store an API key. It does not copy a live FRED series into the repo. FRED's 2024 terms restrict caching and archiving FRED content and prohibit using the API to train models. INGEST-01 does not change that FRED block.

`src/huginn_muninn/evidence.py` reads local JSON only. It does not import a network library. The optional cache is `var/evidence-cache.json`, which `var/` already gitignores. Tests pass a temporary directory. Loading that cache replays each submission through ingest, so a conflict stays a conflict.

## Sources

`fixtures/source_registry.json` stores these assessed limits. EVIDENCE-01 recorded `live_fetch` false on every row. INGEST-01 sets `live_fetch` true for `norges-bank-open-data` and `ecb-sdw`. Statistics Norway and SEC EDGAR stay prepared. FRED stays blocked. Social stays excluded.

- `norges-bank-open-data`. Publisher Norges Bank. Category official statistics. Cadence periodic. The open-data API offers exchange rates and interest rates, including the policy rate, NOWA, and Norwegian government securities. The query service says it can be used freely and requires no authentication. Daily exchange rates are middle rates, indicative rather than binding, published at about 16:00 CET. They are not equity prices and not executable quotes. References: https://www.norges-bank.no/en/topics/statistics/open-data/ and https://www.norges-bank.no/en/topics/Statistics/exchange_rates/
- `ssb-statbank`. Publisher Statistics Norway. Category official statistics. Cadence periodic. The Statbank API is open, requires no registration, and uses CC BY 4.0. PxWebApi v2 limits an extract to 800000 data cells and 30 queries per minute per IP address. It publishes statistics, not security prices. Around the 08:00 publication, revised figures can appear as 0 or a dot between 05:00 and 08:00. References: https://www.ssb.no/en/api and https://www.ssb.no/en/api/pxwebapiv2
- `fred`. Publisher Federal Reserve Bank of St. Louis. Category official statistics. Cadence periodic. An API key is required. The service is economic observations, not a real-time trading feed. The 2024 terms restrict caching, archiving, and wholesale download, and they prohibit use for training machine-learning models. `blocked_reason` is `api_key_and_terms`. Reference: https://fred.stlouisfed.org/docs/api/api_key.html
- `sec-edgar-public`. Publisher U.S. Securities and Exchange Commission. Category filings. Cadence periodic. Public filings and XBRL JSON are available from data.sec.gov. Fair access currently states a maximum of 10 requests per second and requires a declared user agent. Filings are not live prices. Reference: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- `ecb-sdw`. Publisher European Central Bank. Category official statistics. Cadence periodic. EVIDENCE-01 did not verify the license text and recorded `license_status` `not_verified_this_increment`. INGEST-01 records `verified_free_reuse_with_citation`. The reuse policy allows free reuse if the source is quoted and the figures are not modified. Coverage is official statistics, not equity quotes. Reference: https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html
- `social-unverified`. Publisher none. Category excluded. Status excluded. Unverified social-media sentiment is not market evidence. An observation from this source is not stored.

## Fixture and freshness

`fixtures/evidence_observations.json` has `live_retrieval` false and two synthetic observations.

- `obs-usd-nok-2026-03-31` is USD/NOK, unit NOK per 1 USD, value `10.25`, observed and retrieved `2026-03-31`, provenance `synthetic-fixture-not-a-live-norges-bank-retrieval`. At as-of `2026-03-31` and a maximum age of 7 days it is fresh. The desk says that number matches the ledger's supplied 10.25 rate. The match is not a live source confirmation.
- `obs-stale-policy` is the policy rate, unit percent, value `4.50`, observed and retrieved `2026-01-02`, provenance `synthetic-stale-policy-fixture`. At the same as-of and window it is stale.

A value is a `Decimal` parsed from a string, or `None` when the fixture says the value is missing. JSON numbers are rejected, so a float cannot enter. `NaN`, `Infinity`, and `-Infinity` are rejected as `non_finite` and are not stored as amounts. Dates parse with `datetime.date.fromisoformat`. Whitespace-only provenance is blank, and that observation is not stored.

EVIDENCE-01 treated the same observation id and the same value as one stored row, even when the dates differed. The current rule is narrower. A repeat is a duplicate only when observation id, source, subject, unit, value, observation time, retrieval time, provenance, and quality flags all match. The same id with any other field different, including the same Decimal value and a different observation time, is a conflict. Both observations stay visible. The later row is not dropped, and the first is not overwritten. The conflict record shows both observation dates, not only the amounts. Neither value is copied into the ledger.

Freshness uses the caller-supplied as-of date and maximum age. It does not read the wall clock. Fresh means the observation date is on or before as-of, the retrieval date is on or before as-of, and as-of minus the observation date is within the maximum age. Otherwise the flags include `stale`, `future_observation`, or `future_retrieval`. A missing value is not fresh and is not zero.

`assess(store, as_of)` returns limitations only: synthetic fixture, stale, conflict, source not connected, and excluded social source, when each one applies. It has no recommendation field and no probability.

## Open the page

From the checkout root, `python scripts/serve_prototype.py` binds `127.0.0.1:8765`. Open `http://127.0.0.1:8765/evidence`. The desk navigation links to that path. `?date=YYYY-MM-DD` selects the desk date used for freshness. The default is the latest book date.

The page says the desk is in research mode and that the page is not a recommendation. It shows each source as connected, prepared, blocked, or excluded. Norges Bank and the ECB are connected. Statistics Norway and SEC EDGAR are prepared. FRED is blocked. Social is excluded. When the ingest cache has a retrieval timestamp, the page shows that last refresh time. Otherwise it says no live refresh has been stored. It shows freshness, provenance, and any stored error. Ingested USD/NOK points are an inline SVG of stored observations. Missing dates are not interpolated. Recorded points and live points are labeled differently when both exist. The synthetic 10.25 fixture stays labeled synthetic and is not drawn as a Norges Bank point. `POST /evidence/refresh` is a manual refresh, not a scheduler. These observations do not change `Ledger.value`.

The desk home keeps the sentences that confidence, risk, competing interpretations, and a forecast are not assessed. It also says: "Loaded evidence is a recorded synthetic fixture. It does not support a recommendation." The evidence page uses that sentence when no live row is stored. When both kinds are stored, it says rows marked `live_retrieval` were read from the public source, rows marked `synthetic_fixture` were not, and neither kind supports a recommendation.

The page does not emit a buy, sell, hold, or rebalance recommendation. It does not invent a price, a probability, or an expected return. The waveform still does not understand speech.

The parent sandbox, image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, network disabled, discovered 104 tests, 104 passed, exit code 0. A later rerun after the wording clarification also discovered 104 tests, exit code 0.
