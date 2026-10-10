# HM-02 qualified synthetic snapshot

`src/huginn_muninn/snapshot.py` is a separate standard-library snapshot. It does not import or replace `Portfolio`. Amounts and labels in this slice are synthetic.

## Types

- `Holding` stores identity, amount, currency, as_of, and provenance. `add_holding` appends that value and does not copy or coerce its fields.
- `Snapshot` stores `reporting_currency` and `valuation_date` unchanged. It does not case-fold currency and it does not parse dates. `holdings` stays in insertion order.
- `Exclusion` stores an identity and a tuple of reason strings.
- `Qualification` stores `known_subtotal` (`Decimal`), `complete` (`bool`), and `excluded` (a tuple of `Exclusion` values, in insertion order).

`qualify` returns a `Qualification`. It does not remove or reorder holdings.

## Reason order

Every applicable reason is reported, in this stable order:

1. `missing_amount`
2. `non_decimal`
3. `non_finite`
4. `currency_mismatch`
5. `as_of_mismatch`
6. `missing_provenance`

## Exact-match rules

A finite `Decimal` amount enters `known_subtotal` only when currency, as-of, and provenance all pass. Addition uses `Decimal` and is exact. Values are not quantized. Qualification does not read or change the global Decimal context.

- `None` is `missing_amount`. It is not treated as zero, and it is not also `non_decimal` or `non_finite`.
- A value that is not a `Decimal` instance is `non_decimal`. Integers, floats, booleans, and strings are not passed through `Decimal()`.
- A `Decimal` whose `is_finite()` is false is `non_finite`. That covers NaN, Infinity, -Infinity, and signaling NaN. Those values are not added to the known subtotal.
- Currency comparison is exact and case-sensitive. `nok` does not match `NOK`. `None` does not match `NOK`. There is no conversion.
- as-of comparison is exact equality with `valuation_date`. `2026-10-05` does not match `2026-10-06`. Dates are not parsed, and there is no staleness window.
- Provenance must be a non-empty `str`. `""` and `None` are `missing_provenance`. The value is not stripped. A single space is nonempty and can pass this check.

`Decimal(0)` is finite and can qualify when currency, as-of, and provenance pass.

If any reason applies, the holding stays on `snapshot.holdings` and is listed in `excluded`. Its amount is not added. Duplicate identities are both retained and qualified independently.

An empty snapshot qualifies to known subtotal `Decimal(0)`, `complete` true, and no exclusions.

## What complete means

`complete` is true only when `excluded` is empty. It means every stored holding passed the checks above and contributed a finite Decimal amount.

## What this is not

This snapshot is not FX conversion, an exchange rate, an account, a transaction ledger, a journal, tax lots, quantity times price, historical replay, a coverage percentage, a recommendation, a forecast, or allocation advice. It uses synthetic data only.
