# Accounting ledger

This checkout has a synthetic portfolio journal in `src/huginn_muninn/ledger.py`. It is a standard-library prototype. It does not replace the HM-01 `Portfolio` or the HM-02 `Snapshot`. Independent review on 2026-10-10 approved the ledger for this branch.

Run the demonstration from the checkout root:

```text
python scripts/accounting_walkthrough.py
```

Every amount in that trace is synthetic. The output is not a recommendation.

## Journal

`Ledger` stores a reporting-currency label unchanged. Accounts and instruments are registered explicitly. `record` accepts only a deposit, withdrawal, buy, sell, or dividend. Anything else raises `TypeError`.

An event is applied only when every check passes. Rejected events stay available for audit and do not change cash or quantity. Accepted events form a chronological journal: a valid event date strictly earlier than the latest accepted event date is `out_of_order`. The same date may be used again. A repeated event id is `duplicate_id` and is not applied.

Cash and quantity move by exact `Decimal` addition. A buy pays `cash_amount + fee` in `cash_currency`, which may differ from the instrument listing currency. The ledger does not convert currencies at trade time. A sell receives `cash_amount - fee`. If that net is negative, available cash must cover the shortfall. A dividend requires a positive position and changes cash only.

There is no partial fill. A buy that needs more cash than is available, or a sell of more shares than the position holds, is rejected and leaves the books unchanged.

## Historical replay

`books(on_date)` replays accepted events whose event date is on or before `on_date`. An invalid date raises `ValueError`. Zero cash balances and zero quantities are omitted. Remaining rows keep first-seen order. `applied_event_ids` lists the applied ids in journal order. Calling `books` twice with the same date returns equal results. Later events are absent from an earlier date. Replay does not edit the journal.

## Dates and provenance

Transaction date, valuation date, and evidence date are different fields. The ledger does not infer a missing date and it has no staleness window. A date counts only when `datetime.date.fromisoformat` accepts the string. Comparisons use `date` objects.

Provenance counts only when it is a string and `strip()` is non-empty. Empty text, `None`, and whitespace-only text, including a single space, fail with `blank_provenance`. The ledger does not strip a label before storing it.

This is stricter than the HM-02 snapshot. In `snapshot.py`, provenance is nonempty when it is a string of length greater than zero, so a single space still qualifies. That snapshot rule stays in place. The ledger does not change it.

## Valuation and FX direction

`value(on_date)` reads `books(on_date)` and does not mutate the journal. A line enters the known subtotal only with an empty reason list. `reporting_amount` is a `Decimal` in that case and `None` otherwise. The known subtotal is the exact sum of included reporting amounts, or `Decimal(0)` when none qualify. `complete` is true only when every line has empty reasons. An empty book is complete with subtotal zero. A missing price or rate is not entered as zero. The excluded line stays in the result so the holding can be explained.

Cash in the reporting currency contributes its face amount and cites neither a price nor a rate. Other cash needs one `FxRate` whose base is that currency, whose quote is the reporting currency, whose rate date equals `on_date`, and whose evidence date is on or before `on_date`.

A position uses prices whose valuation date equals `on_date`, whose evidence date is on or before `on_date`, and whose provenance is meaningful. Among those eligible prices, a qualifying price has `price_currency` equal to the instrument listing currency. The comparison is exact, including case. One qualifying price is used. Other eligible prices in a different currency stay stored and do not make that line `ambiguous_price`. Two or more qualifying prices produce `ambiguous_price`, with `reporting_amount` `None` and no selected price. Zero qualifying prices, together with one or more eligible prices in another currency, produce `currency_mismatch`. The line cites the earliest added eligible wrong-currency observation id and leaves `reporting_amount` `None`. Several wrong-currency prices still produce `currency_mismatch`. When no observation is eligible, a future evidence date produces `future_evidence`, and no observation produces `missing_price`.

Quantity times price, and a later rate conversion, run in `decimal.localcontext` with precision 28 and `ROUND_HALF_EVEN`. If the listing currency is the reporting currency, that market amount is included and the line cites the price id. Otherwise the same directed rate rule converts the market amount, and the line cites both the price id and the rate id.

The rate means quote currency per 1 base currency. USD base and NOK quote does not create NOK base and USD quote. The ledger does not invert a pair. No rate, or only a future evidence date, leaves `reporting_amount` as `None` with `missing_rate` or `future_evidence`. Two eligible rates for the same pair and date produce `ambiguous_rate`. A price on a different valuation date is not used. FX pair filtering is unchanged.

Caller amounts count only when they are already finite `Decimal` values. `NaN`, `Infinity`, and `-Infinity` are `non_finite`. Integers, floats, booleans, and strings are `non_decimal` and are not coerced. The ledger does not call `getcontext`, does not assign `prec` or `rounding` on the global context, and does not quantize journal amounts or valuation results to cents. The known-subtotal sum uses the same local 28-digit context. Journal addition stays exact `Decimal` addition outside that context. `docs/DECIMAL_RULES.md` records how that differs from HM-01 and HM-02.

## Reconciliation

`reconcile(statement)` compares one account with `books(statement.on_date)`. It does not edit the ledger. Blank statement provenance, an invalid date, or an unknown account yields `reconciled` false and a statement break. Otherwise cash is compared by currency and positions by instrument. A zero on one side and an omission on the other matches. A finite decimal mismatch is `amount_mismatch` and reports both amounts. A non-decimal or non-finite statement amount does not match. A non-zero book row omitted from the statement is `missing_on_statement`. A non-zero statement row absent from the books is `missing_in_books`. Two or more well-typed rows that share a currency or instrument produce one `duplicate_statement_row` break. The book amount is included when the books have that identity, and the statement amount is `None` because the statement has no single amount. That identity does not also produce `amount_mismatch`, `missing_on_statement`, or `missing_in_books`. Identical duplicate amounts still break, `reconciled` is false, and `books` stays unchanged. A row of the wrong type still produces `non_decimal` and does not count as a typed duplicate. `reconciled` is true only when the break list is empty.

## What this phase does not do

Tax lots, cost basis, recommendations, forecasts, fetched market data, and broker connections are absent. The data are synthetic. Nothing here is investment advice, and the ledger does not suggest a trade.

The local pages in `docs/LOCAL_PROTOTYPE.md` call this ledger. They do not keep a second posting, valuation, or reconciliation implementation.
