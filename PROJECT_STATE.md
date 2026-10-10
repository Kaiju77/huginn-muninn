# Project State

## Status

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

## Historical

The following text is the previous awaiting-approval status. It is not the current state.

The Huginn & Muninn project is in the planning phase, awaiting approval of the architecture and the first bounded offline phase.

## Historical next step

Transfer the current product brief and decisions from the ChatGPT project **HUGIIN & MUNIN**, then define the first bounded implementation milestone.
