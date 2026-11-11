# Review log

## 2026-11-11: Codex review round 4 (daily brief)

1. P2: a past brief could show headlines from later. Headlines now appear only when they were fetched on the brief's own date.
2. P2: the quiet-day fallback named a future event. It now uses only events on or before the brief's date.
3. P2: a failed news refresh looked successful. A brief with no fetch from today now says "today's fetch failed or has not run" and shows no old headlines.
4. P2: an empty or malformed GDELT response became "no news" and overwrote the cache. `parse` now raises, so the old file is kept and the step is marked failed.

Regression tests: `CodexRound4Test` in `tests/test_daily_report.py`.

## 2026-11-11: Codex review round 3 (four assets, page, workflow)

1. P2: the page showed a baseline share without n and range. `report.base_rate_rows` now includes `baseline n` and `baseline range %`.
2. P2: a truncated response could overwrite good history. `validate` now rejects data that is stale (latest date over 21 days old), starts after the asset's `starts_by`, or would start later, end earlier or have under 99% of the rows already on disk.
3. P2: `| tee` hid a failing study (no pipefail). The study step now runs in bash with `set -o pipefail`, so a failure stops the job before the commit.

Regression tests: `CodexRound3Test` in `tests/test_prices_pipeline.py`. 261 tests OK. Codex couldn't check WTI, Henry Hub or USD/NOK data because the workflow hadn't run yet.

## 2026-11-11: Codex review round 2 (catalog and loader)

1. P2: Desert Fox began about 22:00 GMT on 16 Dec 1998, after the Brent close. `date_public` changed to 1998-12-17, with the UK Parliament research paper as the source.
2. P2: the Libya uprising was public on 16 Feb 2011 (Benghazi clashes); 17 Feb was the planned day of rage. Changed to 2011-02-16.
3. P2: the Kuwait invasion and Desert Storm are one crisis. Merged into episode `1990-gulf-war` (21 episodes now).
4. P2: malformed CSV rows (extra or missing field, unterminated quote) were accepted silently. Both loaders now parse strictly and check the field count.
5. P3: a UTF-8 BOM broke the header. Both loaders now read `utf-8-sig`.

Regression tests: `CodexRound2Test` in `tests/test_catalog.py` and `PriceCsvStrictnessTest` in `tests/test_brent_pipeline.py`. 243 tests OK.

## 2026-11-11: Codex review of `study.py` (commit b642be3)

All five findings were P2. Each is fixed and has a regression test in `CodexReviewRegressionTest` in `tests/test_study.py`.

1. The era baseline included windows starting after the era ended (the slice happened after invalid windows were dropped). Fixed: windows are filtered by start date before anything else.
2. The baseline line had no n, CI or range. Fixed: the baseline now prints n, rises, share, Wilson CI, median and range, or "too few windows".
3. `min_n` could be set below 8. Fixed: `ValueError`.
4. A horizon of 0, a negative or non-integer horizon, or an empty horizon list passed when there were no events. Fixed: validated up front.
5. NaN/inf prices reached the statistics. Fixed: `sorted_closes` and `summarize` reject non-finite values.

Also adopted: the baseline uses non-overlapping windows, because overlapping windows understate the uncertainty in a Wilson CI (Codex note).

Not a code issue: 107 errors and the failed HTTP check in Codex's run came from its read-only sandbox, which can't create temp directories. Outside the sandbox: 220 tests OK, e2e 12/12.


Independent review on 2026-10-11 approved NOTE-01. Reviewer `9f54c300-bce2-448f-bc4f-edc0ec9d0208` read the observed restatement, the hypothesis label, the citation gates, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 195 tests, 195 passed, exit code 0. This verdict covers notes on the entered book. It is not native acceptance, a recommendation, or a filing match. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved PRICE-01. Reviewer `205dc4e4-7f9f-48cc-a38e-8a79d0059c51` read the accept form, the refusal gates, the evidence loader, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 190 tests, 190 passed, exit code 0. This verdict covers one explicit accept of a stored observation as an entered price. It is not native acceptance, a recommendation, or a ledger rate change. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved VALUE-01. Reviewer `8e1b27f5-d9e5-48d4-afad-f638572be7c4` read the two-date split, the unavailable gates, the locked fee example, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 186 tests, 186 passed, exit code 0. This verdict covers the entered performance page. It is not native acceptance, a recommendation, or a brokerage connection. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved ONBOARD-02. Reviewer `7f37206a-eb44-4416-b904-0ac8267e14b3` read the entered prices, the valuation page, the zero-subtotal sentence, the cash-snapshot overlap, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. An earlier review, `27c4a0ad-95f3-4283-8c02-a883f06c35fd`, rejected the slice because a known NOK subtotal of zero did not show "Allocation is incomplete." That sentence is on the page after the repair. The parent sandbox discovered 178 tests, 178 passed, exit code 0. This verdict covers entered prices and valuation on a selected date. It is not native acceptance, a performance attribution, or a brokerage connection. The synthetic 10.25 rate remains the ledger rate. The listening desk was not restarted.

Independent review on 2026-10-11 approved ONBOARD-01. Reviewer `4290b454-c3f9-4657-aaa3-858d55e48ad3` read the entered book, the ISIN check, the activity mapping, the manual-balance rules, the synthetic separation, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 167 tests, 167 passed, exit code 0. This verdict covers the entered portfolio workflow. It is not native acceptance, a brokerage connection, or a valuation. The synthetic demo remains separate. The listening desk was not restarted.

Independent review on 2026-10-11 approved INGEST-11. Reviewer `03aa61c5-c3d3-44ef-9f33-332065d20934` read the missing-series count, the cache-count sentence, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 154 tests, 154 passed, exit code 0. This verdict covers those page notes. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. The cap remains 500.

Independent review on 2026-10-11 approved INGEST-10. Reviewer `8a53642d-f76a-4fcd-985c-3f1fd545f043` read the cache count, the cap constant, the series quality flags, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 153 tests, 153 passed, exit code 0. This verdict covers the cache count and the quality labels. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. The cap remains 500. This note does not approve INGEST-10.

Independent review on 2026-10-11 approved INGEST-09. Reviewer `1b77f2bb-714f-4adf-9e95-67699efad7cf` read the series due labels, the calendar-day sentence, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 151 tests, 151 passed, exit code 0. This verdict covers those page notes. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. This note does not approve INGEST-09.

Independent review on 2026-10-11 approved INGEST-08. Reviewer `05ef935a-e39b-4b92-990a-0807c762b6bc` read the USD/NOK gap, the inventory freshness labels, the unchanged freshness rule, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 150 tests, 150 passed, exit code 0. This verdict covers the labeled gap and the freshness labels. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-07. Reviewer `93b4999a-71c0-4cca-9ca6-522a66b33861` read the separate policy-rate and NOWA note, the allowlist section, the client constant, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 150 tests, 150 passed, exit code 0. This verdict covers those page notes. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-06. Reviewer `836d93f4-c13a-499b-879f-5a9daf50a79f` read the retrieval dates on the series inventory, the static six-series list, the refresh request order, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 146 tests, 146 passed, exit code 0. This verdict covers those page notes and the named request list. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-05. Reviewer `a3090eaf-710a-40ca-8a86-d26c3075a5c4` read the USD/NOK ledger section, the future-date sentence, the freshness rule, the evidence page, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 145 tests, 145 passed, exit code 0. This verdict covers the newest stored USD/NOK note beside 10.25 and the future-date sentence. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

Independent review on 2026-10-11 approved INGEST-04. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594` read the CPI sentence, the series inventory, the freshness rule, the evidence page, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 137 tests, 137 passed, exit code 0. This verdict covers the monthly CPI sentence and the stored-series inventory. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate. Rendering of stored revisions already existed before this diff.

Independent review on 2026-10-11 approved INGEST-03. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5`. This checkout adds the NOWA chart, the two-source EUR/NOK difference, and the one Statistics Norway CPI cell. That work is not approved by this note.

INGEST-02 was independently reviewed on 2026-10-11. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff` read the refresh, the rate parsers, the revision merge, the due status, the policy chart, the fixtures, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch. The parent sandbox discovered 130 tests, 130 passed, exit code 0. This verdict covers the five-series manual refresh. It is not a live-refresh acceptance or a ledger change. The synthetic 10.25 rate remains the ledger rate.

INGEST-01 was independently reviewed on 2026-10-11. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30` read the ingest package, the evidence identity rule, the evidence page, the registry, the recorded HTTP fixtures, the tests, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite and did not fetch from a public host. The parent sandbox before that review discovered 123 tests, 123 passed, exit code 0. After the review, the evidence page was given a sentence that separates `live_retrieval` rows from `synthetic_fixture` rows, and the evidence-page test was pointed at an empty cache so a local refresh cannot change the fixture assertion. A later parent sandbox discovered 123 tests, 123 passed, exit code 0. This verdict covers the read-only ingestion layer. It is not a live-retrieval pass, a ledger change, or production financial readiness. The synthetic 10.25 fixture remains the ledger rate.

EVIDENCE-01 was independently reviewed on 2026-10-11. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120` read the evidence module, both fixtures, the tests, the evidence page, and the parent receipt. Verdict: approve. The parent sandbox discovered 104 tests, 104 passed, exit code 0. A later parent rerun after a wording clarification also discovered 104 tests, exit code 0. The reviewer did not rerun the suite. This verdict covers the offline evidence register only. Live fetch stays off. The recorded fixture is synthetic. The page is not a recommendation. It is not production financial readiness.

DESK-01 was independently reviewed on 2026-10-11. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958` read the performance replay, the allocation module, the desk, the fixture targets, the waveform script, the tests, and the parent receipt. Verdict: approve. The parent sandbox discovered 89 tests, 89 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the synthetic desk only. It is not production financial readiness. Speech recognition is not implemented. The allocation rows are arithmetic gaps, not recommendations.

HM-01, discoverable accounting tests and explicit incomplete valuation, was independently reviewed on 2026-10-10. Kai then accepted it as a reviewed implementation.

Reviewer task `77d339bf-8bdf-4aaf-bfe9-2147630b425f` read the accounting module, the discoverable tests, `docs/OFFLINE_FOUNDATION.md`, `PROJECT_STATE.md`, `NEXT.md`, the preserved candidate baseline, the canonical Huginn & Muninn handoff, and both unittest receipts. Verdict: approve.

The parent sandbox rerun used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the checkout copied into container scratch and the network disabled. `python -m unittest discover -s tests -v` ran 8 tests, all passed, exit code 0.

This verdict covers that bounded slice only. It does not complete the broader accounting foundation. Currency compatibility, as-of checks, per-holding provenance, conversion, and valuation, exposure, and analytical coverage remain unfinished. `complete=true` means every stored holding is a Decimal. Non-finite Decimal values still count as known. The branch is not integrated into the canonical repository, deployed, or financially activated.

The HM-01 walkthrough demonstrates that accepted slice. It does not extend the 2026-10-10 HM-01 approval to currency, as-of, provenance, conversion, or coverage.

HM-01-WALKTHROUGH was independently reviewed on 2026-10-10. Reviewer `0261868b-647f-4cf2-91bc-db9b8ea7e0e0` read the walkthrough, its tests, the accounting module, the status documents, the HM-02 proposal, the canonical handoff, and the baseline and parent receipts. Verdict: approve. The parent sandbox rerun discovered 13 tests, 13 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the demonstration only. It does not implement or approve HM-02.

HM-02 is implemented in this checkout at `a6c692fb9af18794c1acf7bd038847e8bd7d726a`. Independent review on 2026-10-10 approved it. Reviewer `ed959b8d-9104-4874-a4f1-e085511cdf02` read the snapshot, its tests, the unchanged accounting module, the status documents, and the parent receipt. Verdict: approve. The parent sandbox rerun discovered 26 tests, 26 passed, exit code 0. A later clean-tree rerun of that same commit also discovered 26 tests, 26 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the qualified snapshot only. It does not authorize conversion, transactions, forecasts, recommendations, or HM-03.

The accounting ledger in `src/huginn_muninn/ledger.py` was independently reviewed on 2026-10-10. Reviewer `6e908566-155a-4fbf-9755-3d40359c1995` read the ledger, its tests, the walkthrough, the unchanged HM-01 and HM-02 modules, and the parent receipt. Verdict: approve. The parent sandbox discovered 57 tests, 57 passed, exit code 0. The reviewer did not rerun the suite. This verdict covers the synthetic ledger only. It does not authorize tax lots, recommendations, forecasts, or a further phase. At that review, a repeated statement row kept the first amount. PROTOTYPE-01 later changes that behavior, and its own review is recorded separately.

PROTOTYPE-01 was independently reviewed on 2026-10-10. Reviewer `55bf7095-d00c-40fd-a475-d7d8b1b5932c` read the ledger changes, the prototype, the fixture, the tests, the decimal and local-prototype notes, and the parent receipt. Verdict: approve. The parent sandbox discovered 75 tests, 75 passed, exit code 0. A later parent rerun, after table cells were kept on one line, again discovered 75 tests, exit code 0. The reviewer did not rerun the suite. This verdict covers the synthetic paper ledger only. It is not production financial readiness. A rejected event id still cannot be reused. The pages do not accept a new price or FX rate; those stay in the fixture. There is no cost basis.

## Historical

The following sentence is the earlier review note. It is not the current HM-01 verdict.

All completed planning artifacts retained with hashes. A bounded synthetic-data offline accounting foundation contract is saved for review. Architecture and implementation remain unapproved.
