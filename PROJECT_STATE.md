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

## Historical

The following text is the previous awaiting-approval status. It is not the current state.

The Huginn & Muninn project is in the planning phase, awaiting approval of the architecture and the first bounded offline phase.

## Historical next step

Transfer the current product brief and decisions from the ChatGPT project **HUGIIN & MUNIN**, then define the first bounded implementation milestone.
