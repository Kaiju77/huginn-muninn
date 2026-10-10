# HM-01 walkthrough

This demonstration calls the accepted Portfolio API and prints the results. It does not change accounting behavior, and it is not HM-02.

Every amount in the output is synthetic. `get_total_value` treats a stored `Decimal` as the value itself. It does not multiply quantity by price. The output does not give investment advice, percentages, or recommendations.

## How to run

The verified command is the offline sandbox. The image is `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`. The network is disabled. The checkout is mounted read-only at `/snapshot`. The container copies that tree into its own scratch directory and runs the walkthrough and the tests there.

```
docker run --rm --network none --entrypoint sh -v C:/Users/kaiar/Documents/projects/cursor-worktrees/hm-01:/snapshot:ro sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f -c 'mkdir -p /tmp/hm01 && cp -a /snapshot/. /tmp/hm01/ && cd /tmp/hm01 && python scripts/hm01_walkthrough.py && python -m unittest discover -s tests -v'
```

A local `python scripts/hm01_walkthrough.py` from the checkout root runs the same standard-library program. The script lives in `scripts/`, so it places the checkout root on `sys.path` before importing `src.huginn_muninn.accounting`.

## What each STEP means

`STEP representation` is an empty portfolio. `currency` and `as_of` are labels on that object. `assets` is the number of stored entries, which is zero.

`STEP stored` follows two `add_asset` calls. The key `cash` is only a dictionary identity, not an account. `broad-fund` is the same kind of identity. Both stored values are `Decimal` instances.

`STEP overwrite` calls `add_asset` again for `cash`. The new `Decimal` replaces the previous one. There is no journal, so the earlier cash amount is not retained. `prior_cash_retained=False` records that comparison.

`STEP valuation` is `get_total_value` for those two finite Decimals. `known_subtotal` is their exact sum. `complete=True` means every stored holding is a `Decimal`. `unknown=()` means no holding was left out. The returned valuation is not itself a `Decimal`.

`STEP incomplete` stores a non-Decimal string and `None` beside the two Decimals. The known subtotal stays the sum of the Decimals. `complete=False`. `unknown` names `private-note` and `missing-quote` in insertion order. `retained_private` and `retained_missing` are the objects `get_asset` still returns.

`STEP history` changes the as-of label to `2025-01-01`. Cash remains the overwritten amount. `reconstructed=False` because the label change does not restore the replaced value. The walkthrough states that historical reconstruction is not implemented.

`STEP currency_label` changes the currency label to `USD`. The known subtotal is unchanged. `converted=False` because the API does not convert.

`STEP non_finite_nan` and `STEP non_finite_infinity` each use a fresh portfolio with a finite `Decimal('10')` plus `Decimal('NaN')` or `Decimal('Infinity')`. Both non-finite values are still `Decimal` instances, so `complete` stays true, `unknown` stays empty, and the known subtotal becomes `NaN` or `Infinity`. The walkthrough states that non-finite Decimal values still count as known.

`STEP absent` reports features the API does not provide. Each flag is false: accounts, transactions, cash flows, reconciliation, provenance, conversion, historical replay, coverage, and advice.
