# Huginn & Muninn

Local implementation repository for the ChatGPT project **HUGIIN & MUNIN**.

This repository is prepared for the shared AI development harness. Product scope and implementation decisions should be captured in `PROJECT_STATE.md` before feature work begins.

This isolated `cursor/hm-01` branch preserves the accepted HM-01 slice: discoverable synthetic tests and an explicit known Decimal subtotal with completeness. The HM-01 `Portfolio` still does not qualify currency, as-of, or provenance. The separate HM-02 snapshot does. Conversion and coverage qualification remain unfinished. The branch is not merged into the canonical Huginn & Muninn repository.

## Run the HM-01 walkthrough

From the checkout root, `python scripts/hm01_walkthrough.py` prints the synthetic demonstration. What the output means, and the offline sandbox command, are in `docs/HM01_WALKTHROUGH.md`.

`docs/HM02_SNAPSHOT.md` describes the separate qualified snapshot in this checkout. Independent review approved that snapshot on this branch. It is not merged.

## Run the accounting walkthrough

From the checkout root, `python scripts/accounting_walkthrough.py` prints the synthetic ledger trace. The journal rules are in `docs/ACCOUNTING_LEDGER.md`.

## Run the local prototype

From the checkout root, `python scripts/serve_prototype.py` binds `127.0.0.1:8765` and prints `http://127.0.0.1:8765/`. The paper pages and the synthetic fixture are described in `docs/LOCAL_PROTOTYPE.md`. Decimal precision is in `docs/DECIMAL_RULES.md`. The figures are synthetic. The page is not a recommendation.

## Desk

`GET /` is the night desk from DESK-01. Average-cost performance, arithmetic gaps, the conversation form, and the still waveform are described in `docs/DESK.md`. The hosted FastAPI, React, and PostgreSQL target remains deferred because this milestone cannot install dependencies. The desk does not recommend a transaction, forecast a return, or recognize speech. Independent review on 2026-10-11 approved DESK-01. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958`.

## Evidence

`GET /evidence` is linked from the desk. It reads `fixtures/source_registry.json`, the recorded synthetic fixture in `fixtures/evidence_observations.json`, and any stored public refresh under `var/ingest-cache/`. Norges Bank, the ECB, and Statistics Norway are connected. An explicit refresh can store USD/NOK, EUR/NOK, the policy rate, NOWA, ECB NOK/EUR, and one Statistics Norway CPI cell, table 14700 for 2026M07 total. The evidence page draws stored NOWA points and, where both EUR/NOK observations exist for a date, shows the Norges Bank minus ECB difference. That difference is not a recommendation and is not copied into the ledger. When `ssb-cpi-total-2026M07` is visible, the page says: "The CPI date is the first day of 2026M07. Stale in October means the monthly index is older than 7 days. It is not a failed daily refresh." The freshness rule is unchanged, and that row stays stale against 2026-10-11. The page also lists each stored subject once, with its source id, the latest observation date among visible rows, and the value on that date. If two rows share the latest date, both values are shown and the line says the date has more than one row. The inventory is computed from stored rows only. Independent review on 2026-10-11 approved INGEST-04. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594`. Each connected source is printed as current or due from stored rows only. Other SSB tables remain unconnected. SEC EDGAR is prepared. FRED is blocked. Social is excluded. The page is not a recommendation. See `docs/EVIDENCE.md`, `docs/INGEST.md`, and `HUMAN_TASKS.md`. Independent review on 2026-10-11 approved EVIDENCE-01. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120`. Independent review on 2026-10-11 approved INGEST-01. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30`. Independent review on 2026-10-11 approved INGEST-02. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff`. Independent review on 2026-10-11 approved INGEST-03. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5`. A stored public observation is not copied into the ledger.
