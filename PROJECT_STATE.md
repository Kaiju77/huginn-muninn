# Project State

## Status

INGEST-01 is a reviewed read-only ingestion layer on branch `cursor/hm-01` at `d9cad72ab052ca6d1e2517c4d7ebef918e783a3c` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`. The baseline before these edits was `578c23c7f08059f5bf53acb4bced9e8441a52ae2`, and the worktree was clean. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30` approved it. This status is not canonical integration, deployment, or production financial readiness.

Norges Bank and the ECB are connected for one explicit manual refresh. Statistics Norway and SEC EDGAR are prepared. FRED stays blocked, and it is not on the allowlist. Unverified social sentiment stays excluded. A repeated observation is a duplicate only when every identity field matches, including the observation date. The same id with a different date is a conflict, and both dates stay visible. Ingested observations are not copied into the ledger. The synthetic USD/NOK rate remains 10.25. `accounting.py`, `snapshot.py`, `ledger.py`, and `allocation.py` were not edited. The rules are in `docs/INGEST.md`.

The implementer sandbox and a later parent rerun used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 123 tests, 123 passed, exit code 0. Those runs did not call the network. A separate parent refresh on 2026-10-11 posted the window 2026-10-01 through 2026-10-09 to the local desk. Last refresh `2026-10-11T08:03:34+00:00`. Norges Bank `nb-exr-USD-NOK-2026-10-09` is 9.5623 NOK per 1 USD, observed 2026-10-09, retrieved 2026-10-11, quality `live_retrieval`, fresh against 2026-10-11. ECB `ecb-exr-NOK-EUR-2026-10-09` is 10.7155 NOK per 1 EUR on the same dates, also `live_retrieval` and fresh against 2026-10-11. The ledger rate stayed 10.25. That retrieval is not an offline test result.

EVIDENCE-01 is a reviewed local evidence register on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`. The baseline before those edits was `3079c1b69d19f9512691d4fb244f5cdf834b16a2`, and the worktree was clean. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120` approved it. This status is not canonical integration or production financial readiness.

At EVIDENCE-01, live fetch stayed off. `src/huginn_muninn/evidence.py` ingests `fixtures/evidence_observations.json` and reads `fixtures/source_registry.json`. That module still does not fetch. The observations are not copied into the ledger, and the evidence page does not change `Ledger.value`. `accounting.py`, `snapshot.py`, their tests, `tests/test_hm01_walkthrough.py`, and `scripts/hm01_walkthrough.py` were not edited. The rules are in `docs/EVIDENCE.md`.

DESK-01 is a reviewed local night desk on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958` approved it on 2026-10-11. This status is not canonical integration or production financial readiness.

Kai accepted HM-01 as a reviewed implementation on branch `cursor/hm-01` in `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01`. Reviewer task 77d339bf-8bdf-4aaf-bfe9-2147630b425f approved the bounded slice. This local preservation is not canonical integration, deployment, or completion of the broader accounting milestone.

The accounting module returns an explicit known Decimal subtotal, a completeness flag, and the identities of retained missing or non-Decimal holdings. It no longer mutates the global Decimal context. Discoverable `unittest` cases cover the synthetic known cases, an exact multi-holding subtotal, the incomplete-valuation regression, and context preservation.

Offline tests in this checkout: `python -m unittest discover -s tests -v` inside image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, network disabled, source copied into container scratch. The implementer receipt and a later parent rerun each executed 8 tests, 8 passed, 0 failed, exit code 0. Evidence: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/HM-01/unittest.txt` and `unittest-review-parent.txt`. The reviewer inspected those receipts and did not rerun the suite.

Currency compatibility, as-of checks, per-holding provenance, conversion, and valuation, exposure, and analytical coverage remain unfinished. HM-01 did not solve them.

## Walkthrough verification — 2026-10-10

HM-01-WALKTHROUGH adds a synthetic demonstration of the accepted Portfolio API on this isolated checkout. HEAD before the demonstration was `a718922de94aebfc4a44b5e38e3ab3b7bd4cd7a4` (`a718922`) and the worktree baseline was clean. The demo uses the existing API only. It does not change Portfolio behavior.

The offline sandbox image is `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the network disabled, the checkout mounted read-only, and the program and tests copied into container scratch. The implementer and a later parent rerun each ran the walkthrough and then `python -m unittest discover -s tests -v`. Both discovered 13 tests, 13 passed, exit code 0. Parent receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/HM-01-WALKTHROUGH/unittest-parent.txt`. Baseline before the demo: `unittest-baseline.txt` in the same directory, 8 tests, exit 0.

Fresh reviewer `0261868b-647f-4cf2-91bc-db9b8ea7e0e0` approved the walkthrough. Implementer `b034aca5-bf35-4590-9a9d-12cc248bee36` made the edit. The reviewer read the source and receipts and did not rerun the suite. These walkthrough files are preserved on top of `a718922`. The walkthrough review itself did not authorize HM-02.

Accounts, transactions, cash flows, reconciliation, provenance, conversion, historical replay, and coverage are not implemented. Non-finite Decimals still count as known.

See `docs/HM01_WALKTHROUGH.md` for how to run the demonstration and what each STEP line means. At the time of that walkthrough, `docs/HM02_PROPOSAL.md` was only a proposal. The HM-02 section below records the later authorization.

## HM-02 qualified snapshot — 2026-10-10

Kai authorized HM-02 on 2026-10-10 with case-sensitive currency matching, exact as-of equality, required nonempty provenance, and a separate snapshot type. The reviewed HM-01 walkthrough remains at commit `9a733369447c9e329a53e843de6e14526049acb5`.

`src/huginn_muninn/snapshot.py` is a separate standard-library snapshot. A finite Decimal amount enters the known subtotal only when currency, as-of, and provenance all pass. Reason strings, in stable order, are missing_amount, non_decimal, non_finite, currency_mismatch, as_of_mismatch, and missing_provenance. Every other holding stays stored and is reported with those reasons. Non-finite values do not enter the known subtotal. `src/huginn_muninn/accounting.py` and the HM-01 tests are unchanged.

Independent review approved this implementation. Reviewer `ed959b8d-9104-4874-a4f1-e085511cdf02` read the snapshot, its tests, the unchanged accounting module, the status documents, and the parent receipt. Verdict: approve. The parent sandbox rerun discovered 26 tests, 26 passed, exit code 0. Receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/HM-02/unittest-parent.txt`. The reviewer did not rerun the suite. This acceptance is local to `cursor/hm-01`. It is not canonical integration, and it does not authorize HM-03.

The implementation commit is `a6c692fb9af18794c1acf7bd038847e8bd7d726a`. A clean-tree rerun of that commit, on the same image with the network disabled, again discovered 26 tests, 26 passed, exit code 0. Receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/HM-02/unittest-clean-head.txt`. `accounting.py` has no diff from `a718922de94aebfc4a44b5e38e3ab3b7bd4cd7a4` through this commit.

The implementer final run and the parent rerun both used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the network disabled and the checkout copied into container scratch. An earlier implementer run discovered 25 tests and exited 1 because a precision test reloaded the snapshot module. That reload was removed before the passing 26-test run. Implementer `e14de7f7-3703-4a79-9395-c747b961f1bf` wrote the snapshot.

The known subtotal uses ambient Decimal precision and does not change that precision. A caller who has already lowered precision can still round a large sum. A single space counts as nonempty provenance. `Portfolio` still treats non-finite Decimals as known. Conversion, transactions, coverage percentages, forecasts, and recommendations are not in this slice.

## Accounting ledger — 2026-10-10

Kai authorized an offline synthetic accounting phase, task ACCOUNTING-LEDGER, on this isolated checkout. HEAD before the ledger edits was `a804f40181d5d8a89dd7f60982c5b63b936d18a8`. The worktree was clean. HM-01 and HM-02 were not reimplemented. `accounting.py`, `snapshot.py`, and their tests are unchanged.

`src/huginn_muninn/ledger.py` posts synthetic accounts, cash, holdings, trades, dividends, supplied prices, and directed FX rates. It replays historical books, values only qualified observations, and reconciles synthetic statements. A single space is blank provenance in the ledger. The HM-02 snapshot still treats a single space as nonempty.

Independent review approved this ledger. Reviewer `6e908566-155a-4fbf-9755-3d40359c1995` read the ledger, its tests, the walkthrough, the unchanged HM-01 and HM-02 modules, and the parent receipt. Verdict: approve. The parent sandbox discovered 57 tests, 57 passed, exit code 0. Receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/ACCOUNTING-LEDGER/unittest-parent.txt`. The reviewer did not rerun the suite. The ledger commit is `66a3e7644a2d74ebc749667fa88f94b27b721280`. This acceptance is local. It is not canonical integration, and it does not authorize a further phase.

Known limits recorded at that review, before PROTOTYPE-01: a repeated statement row kept the first amount, a wrong-currency price could be reported as `ambiguous_price`, and valuation followed ambient Decimal precision. A rejected event id cannot be reused. The ledger has no tax lots, cost basis, or staleness window. `Decimal("10.5")` can print a trailing `.0` while remaining an exact Decimal. The prototype section records the later changes.

The rules are in `docs/ACCOUNTING_LEDGER.md`. The synthetic trace is `python scripts/accounting_walkthrough.py`.

The implementer sandbox run and the parent rerun both used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 57 tests, 57 passed, exit code 0. An earlier implementer run discovered 57 tests and exited 1 because statement positions were read through a cash amount field. That comparison was corrected before the passing runs. Implementer `0fa10054-f14b-46c7-80ec-c2659e5fe82f` wrote the ledger.

## Local prototype — 2026-10-10

Kai authorized PROTOTYPE-01, an offline synthetic prototype, on 2026-10-10. The isolated checkout is `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01` on `cursor/hm-01`. HEAD before these edits was `23c943ad50a88b4a0eb71fcd964798c9ddb321c4`, and the worktree was clean. HM-01 and HM-02 source files were not edited.

`src/huginn_muninn/ledger.py` now emits `duplicate_statement_row` when a statement repeats a currency or instrument, selects one listing-currency price before treating other currencies as ambiguity, and computes valuation products and the known subtotal inside a local 28-digit Decimal context. Journal addition stays outside that context. `docs/DECIMAL_RULES.md` records that HM-01 and HM-02 still use ambient precision.

`src/huginn_muninn/prototype.py` and `scripts/serve_prototype.py` are a standard-library local interface. The committed fixture is `fixtures/synthetic_portfolio.json`. The runtime overlay is `var/synthetic-book.json`. The hosted FastAPI, React, and PostgreSQL target stays deferred because this milestone cannot install dependencies. See `docs/LOCAL_PROTOTYPE.md`.

Independent review approved PROTOTYPE-01. Reviewer `55bf7095-d00c-40fd-a475-d7d8b1b5932c` read the ledger changes, the prototype, the fixture, the tests, and the status documents. Verdict: approve. The reviewer did not rerun the suite. After that review, table cells stopped breaking mid-word and the page scrolls wide tables. That layout change does not alter posting, valuation, or reconciliation. A parent sandbox rerun after the layout change discovered 75 tests, 75 passed, exit code 0. A local browser session opened `http://127.0.0.1:8765/`, read the incomplete 2026-03-10 valuation, the 15050 versus 15051 reconciliation, and the chart, posted a synthetic 100 NOK deposit, and reloaded the fixture. The paper-ledger commit is `afcd004c1a04f93711b4dac1163bf3d8a4c61996`. This acceptance is local. It is not canonical integration, production financial readiness, or a further phase.

The implementer sandbox used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 75 tests, 75 passed, exit code 0. A later parent rerun of the same dirty tree discovered 75 tests, 75 passed, exit code 0. Receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/PROTOTYPE-01/unittest-parent.txt`. Implementer `b3fcf9be-096e-451e-820f-685f7b45ecc1` wrote the prototype. The parent rerun is not an independent review.

## Desk — 2026-10-11

Kai authorized DESK-01 on 2026-10-11. The isolated checkout is `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01` on `cursor/hm-01`. HEAD before these edits was `0ada7b5904d76920128b98e89339eb92bcdda752`, and the worktree was clean. `accounting.py`, `snapshot.py`, their tests, `tests/test_hm01_walkthrough.py`, and `scripts/hm01_walkthrough.py` were not edited.

`Ledger.performance` replays average cost in the cash currency paid. A mixed cash currency makes that cost unknown. Realized and unrealized gains stay unknown when the cost or the market amount cannot be stated in one currency without inventing a rate. The residual is an accounting identity, not a return. `src/huginn_muninn/allocation.py` compares a complete valuation with the fixture's target weights and labels listing-currency exposure. It does not recommend a transaction.

`GET /` is a server-rendered night desk. The paper home remains `GET /ledger`. `GET /api/desk` returns the same known subtotal as `Ledger.value`. `GET /conversation` appends a deterministic text reply and shows a still waveform. Speech recognition, speech synthesis, and a live conversation model are not implemented. The hosted FastAPI, React, and PostgreSQL target remains deferred because this milestone cannot install dependencies.

The rules are in `docs/DESK.md` and `docs/ACCOUNTING_LEDGER.md`. Independent review approved this desk. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958` read the performance replay, the allocation module, the desk, the fixture targets, the waveform script, and the tests. Verdict: approve. The reviewer did not rerun the suite. The parent sandbox discovered 89 tests, 89 passed, exit code 0. Receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/DESK-01/unittest-parent.txt`. A local browser session opened the desk, read the 24932.50 known subtotal, the 1432.50 residual, the price and rate citations, and the empty intelligence slots, then received a refusal for "Should I buy Harbor?". This acceptance is local. The night-desk commit is `83750c9c6ec98a48fd24c864ee2cea184a37cf15`.

The implementer sandbox used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 89 tests, 89 passed, exit code 0. An earlier run in the same image discovered 89 tests and exited 1 because average-cost addition still followed the caller's lowered precision. That addition was moved into the local 28-digit context before the passing run.

## Evidence — 2026-10-11

Kai authorized EVIDENCE-01 on 2026-10-11. The isolated checkout is `C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01` on `cursor/hm-01`. HEAD before these edits was `3079c1b69d19f9512691d4fb244f5cdf834b16a2`, and the worktree was clean.

The source registry records Norges Bank, Statistics Norway, FRED, SEC EDGAR, the ECB, and an excluded social source. In that increment every source had `live_fetch` false. FRED stays blocked because an API key is required and the 2024 terms restrict caching, archiving, and wholesale download, and prohibit use for training machine-learning models. The ECB license text was not verified in that increment. INGEST-01 later records the ECB reuse policy as verified free reuse with citation. Unverified social-media sentiment is not stored.

The recorded fixture has two synthetic observations and `live_retrieval` false. At 2026-03-31 with a maximum age of 7 days, USD/NOK `10.25` is fresh and the policy rate `4.50` from 2026-01-02 is stale. The fresh number matches the ledger's supplied 10.25 rate. That match is not a live source confirmation. In that increment, a repeated observation stayed one row when the id and the value matched. INGEST-01 keeps a repeat as one row only when every identity field matches. A different value for the same id is a conflict, and both amounts stay visible. A different observation date for the same id and the same value is also a conflict, and both dates stay visible. Neither value is written into the ledger.

`GET /evidence` server-renders the registry and the fixture. The desk stays in research mode. The intelligence block says the recorded fixture is not a competing interpretation, that confidence, risk, and a forecast are not assessed, and that the loaded evidence does not support a recommendation. After review, the earlier sentence "No competing evidence is loaded" was replaced so the page does not say the fixture is both absent and loaded. A later parent sandbox rerun after that wording change discovered 104 tests, exit code 0.

Independent review approved this register. Reviewer `607f9f92-2ef6-49c8-a699-0e3e8ab9e120` read the evidence module, both fixtures, the tests, the evidence page, and the parent receipt. Verdict: approve. The reviewer did not rerun the suite. The parent sandbox discovered 104 tests, 104 passed, exit code 0. Receipt: `C:/Users/kaiar/Documents/projects/cursor-portfolio/evidence/EVIDENCE-01/unittest-parent.txt`. Implementer `426d66ce-5391-43cb-a69b-2683f76b84fc` wrote the register. This acceptance is local. The evidence-register commit is `1f6f26750c0b196aaea57d2f70c9edb2833628d7`.

## Historical

The following text is the previous awaiting-approval status. It is not the current state.

The Huginn & Muninn project is in the planning phase, awaiting approval of the architecture and the first bounded offline phase.

## Historical next step

Transfer the current product brief and decisions from the ChatGPT project **HUGIIN & MUNIN**, then define the first bounded implementation milestone.
