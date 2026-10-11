# Roadmap

Huginn & Muninn is a local research desk. These four milestones are the product path. The synthetic Northline and Harbor book stays the demo on the existing pages until a person uses the entered portfolio instead.

## 1. Portfolio onboarding

A person enters their own accounts, instruments, contributions, withdrawals, purchases, sales, fees, dividends, and manual balances. ONBOARD-01 is this slice: a separate entered store, replayed through the existing ledger, with the synthetic demo left in place. Independent review on 2026-10-11 approved ONBOARD-01. Reviewer `4290b454-c3f9-4657-aaa3-858d55e48ad3`. Later onboarding work can add editing and import. Brokerage connections are not part of onboarding.

## 2. Valuation and performance

Value a holding from a supplied price times quantity, or from a dated manual balance. A missing price stays unknown. A manual snapshot does not claim full attribution.

ONBOARD-02 records a price on an entered instrument and values that book on a selected date. Cash stays at face in its own currency. One matching price on that date sets a quantity's value. Two prices on that date are ambiguous. A missing price stays unknown. A manual balance is a snapshot on its as-of date and is not priced. Allocation shares are shown only when every line on that date is known, every line is in NOK, and the known NOK subtotal is not zero. Otherwise, including a known NOK subtotal of zero and an empty date, the page says "Allocation is incomplete." and shows no shares. Independent review on 2026-10-11 approved ONBOARD-02. Reviewer `7f37206a-eb44-4416-b904-0ac8267e14b3`.

VALUE-01 separates contributions, withdrawals, fees, and dividends from the change in value between two dates on the entered book. The page is GET /portfolio/performance, linked from the entered valuation page. Flows are activities strictly after the start date and on or before the end date. Purchases and sales stay inside the two valuations; only their fees are fees. A fee is cash leaving, not a market gain. A dividend is cash received. It is not a contribution and it is not a price change. The page does this only when both dates are fully known NOK quantities times one same-currency price, or known NOK cash, and the book has no manual balance. Otherwise it says "Attribution is unavailable." and shows no price-change figure. It does not convert currencies and it does not fill a missing price. Independent review on 2026-10-11 approved VALUE-01. Reviewer `8e1b27f5-d9e5-48d4-afad-f638572be7c4`.

## 3. Market intelligence

Practical adapters for filings, macro releases, permitted prices, and verified news. No unlicensed scrape.

## 4. Portfolio-aware notes

Notes keep observed facts separate from hypotheses. No recommendations until a later explicit authorization.
