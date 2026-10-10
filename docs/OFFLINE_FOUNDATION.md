# Offline Foundation

This checkout contains the accepted HM-01 slice: a bounded standard-library portfolio snapshot. Fixtures and amounts are synthetic. HM-01 records an explicit known Decimal subtotal and says whether that numeric valuation is complete. Acceptance of this slice does not complete the offline foundation, and it does not activate financial services.

## Known subtotal and completeness

`Portfolio.get_total_value` returns a `Valuation` with:

- `known_subtotal`: the exact sum of stored holdings whose values are `Decimal`. An empty portfolio has known subtotal `Decimal(0)`. Decimal holdings still sum exactly.
- `complete`: true only when every stored holding is a `Decimal`. A missing value (`None`), a non-Decimal value, or any other non-Decimal holding makes the valuation incomplete.
- `unknown_holdings`: the identities of those retained holdings, in portfolio order. The holdings stay on the portfolio and are not dropped.

The known subtotal is not returned as a bare total. Callers cannot treat that number as a silently complete portfolio value.

Importing or using the accounting module does not set the global Decimal context. Local arithmetic uses Decimal's default precision and does not mutate `getcontext()`.

`get_asset`, `set_currency`, and `set_as_of` keep their previous known-case behavior. Currency and as-of remain single portfolio-level labels.

## Unfinished — this task did not solve these

HM-01 did not implement:

- currency compatibility
- as-of checks
- per-holding provenance
- conversion, including qualified externally supplied conversion inputs
- valuation coverage
- exposure coverage
- analytical coverage

`complete=true` means every stored holding was a Decimal. It does not mean currency, as-of, provenance, conversion, or coverage qualification passed. Non-finite Decimal values, such as NaN and infinity, still count as known; that limit is recorded and was not part of the accepted repair.

No percentage advice, optimization, tax engine certification, return assumptions, forecast skill claims, personalized policy defaults, or tactical activation. No FastAPI/PostgreSQL/React runtime provisioning, data vendor/broker/API connections, purchases, private financial imports, services, deployment, or merge/push.
