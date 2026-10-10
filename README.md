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
