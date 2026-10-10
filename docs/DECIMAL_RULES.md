# Decimal rules

Ledger valuation uses `decimal.localcontext` with `Context(prec=28, rounding=ROUND_HALF_EVEN)`.

28 is Python's default significant-digit precision. `ROUND_HALF_EVEN` applies when an operation exceeds 28 significant digits. It is a significant-digit rule. It is not a money-cent rule. FX rates may have more than two decimal places. Stored results remain `Decimal` values. `localcontext` restores the caller's context when the block ends.

These operations run inside that context:

- quantity times price
- a market amount times a directed FX rate
- a foreign-cash amount times a directed FX rate
- the known-subtotal sum
- the sold fraction of average cost, cost times quantity sold divided by quantity held
- realized gain, proceeds minus that removed cost, when the gain is known
- unrealized gain, reporting amount minus cost, or minus cost times one directed rate
- the accounting residual, known subtotal minus accepted deposits plus accepted withdrawals
- an allocation weight, current amount divided by the known subtotal
- an illustrative amount, target weight times the known subtotal minus the current amount

Journal addition stays exact `Decimal` addition outside that context. A deposit, withdrawal, buy, sell, or dividend moves cash and quantity by addition, so those postings do not enter the local context. Average-cost addition of `cash_amount + fee`, and subtraction of the removed fraction, run in the local 28-digit context so a caller who has lowered precision does not round the cost.

The ledger does not call `getcontext`. It does not assign `prec` or `rounding` on the global context. It does not quantize journal amounts or valuation results to cents.

HM-01 `Portfolio.get_total_value` and HM-02 `Snapshot.qualify` still add with the caller's ambient Decimal precision. PROTOTYPE-01 does not change those modules. A caller who has already lowered precision can still round a large HM-01 or HM-02 sum. `Ledger.value` computes its products and known subtotal at 28 significant digits, then restores the caller precision.
