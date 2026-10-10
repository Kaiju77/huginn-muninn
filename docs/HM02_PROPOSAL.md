# HM-02 proposal — qualified synthetic snapshot holdings

Kai authorized this proposal on 2026-10-10 with case-sensitive currency matching, exact as-of equality, required nonempty provenance, and a separate snapshot type.

Implementation is in `src/huginn_muninn/snapshot.py`. Independent review on 2026-10-10 approved it for this isolated branch. Reviewer `ed959b8d-9104-4874-a4f1-e085511cdf02`. The parent sandbox discovered 26 tests, 26 passed, exit code 0. This acceptance is not a merge, and it does not start HM-03.

## Historical proposal

Status: proposed on 2026-10-10. Not authorized. Not implemented.

## Why this slice

HM-01 stores arbitrary values under string keys and sums Decimal instances, including NaN and Infinity. The approved first synthetic-data milestone still requires explicit currency, as-of, and provenance, and it forbids treating missing or unqualified values as a complete total. A transaction ledger, FX conversion, and coverage percentages are larger and would sit on unqualified numbers if built now. The next smallest useful milestone is a separate qualified snapshot that includes an amount in the known subtotal only when every qualification check passes, while every other holding stays visible with reasons.

## Proposed later scope

This scope waits for a future authorization.

- Add a new standard-library module. Leave `Portfolio.get_total_value` and the HM-01 tests unchanged.
- Holding fields: identity, amount, currency, as_of, provenance.
- Snapshot fields: reporting_currency, valuation_date, holdings in insertion order.
- A qualification result: known_subtotal, complete, and excluded holdings with one or more reasons.
- Reasons: missing_amount, non_decimal, non_finite, currency_mismatch, as_of_mismatch, missing_provenance.
- Include the amount only when the reason list is empty.
- Finite means `Decimal.is_finite()`. NaN, Infinity, and -Infinity are non_finite and must not poison the known subtotal.
- Currency match is exact and case-sensitive. Do not convert.
- as_of match is exact string equality with the snapshot valuation date. No staleness window.
- Provenance must be a non-empty string label. It is not an evidence document store.
- A missing amount is not zero.
- complete is true only when every holding qualifies. An empty snapshot has known_subtotal `Decimal(0)` and complete true.
- Do not mutate the global Decimal context.
- Multiple defects on one holding are all reported.

## Acceptance criteria

For that future implementation:

- Discoverable unittest only, standard library.
- Two qualified NOK holdings sum exactly.
- Each exclusion reason has a fixture that retains the holding, excludes it, and sets complete false.
- Two defects on one holding report both reasons.
- NaN, Infinity, and -Infinity do not enter the known subtotal.
- USD against reporting currency NOK is currency_mismatch and is not converted.
- as_of 2026-10-05 against valuation date 2026-10-06 is as_of_mismatch.
- Empty provenance and a missing amount are excluded.
- Global Decimal precision is unchanged.
- The existing HM-01 tests still pass.
- Offline image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, network disabled, nonzero discovered test count, exit 0.
- No new dependency.

## Dependencies

Accepted HM-01 behavior. Architecture sections 3, 8, and 24 in the canonical handoff are direction only. The 2026-10-08 first-phase contract applies. No external data.

## Explicitly outside HM-02

FX conversion even with a supplied rate; accounts; transactions; cash-flow journals; tax lots; quantity times price; historical replay; broker reconciliation; valuation, exposure, and analytical coverage percentages; the provisional 95 percent threshold; corporate actions; fees; dividends; recommendations; forecasts; allocation advice; persistence; FastAPI; PostgreSQL; React; live accounts; credentials; purchases.

## Unresolved decisions

These are decisions for Kai, not silent defaults.

- Confirm exact case-sensitive currency match and exact as-of equality, with no FX and no staleness window in HM-02.
- Confirm provenance is a required non-empty label, not a document store.
- Confirm HM-02 adds a new snapshot type and does not replace Portfolio.
- The milestone after HM-02 is not chosen here. Supplied-rate conversion and a cash-and-quantity ledger both wait until qualification exists.
