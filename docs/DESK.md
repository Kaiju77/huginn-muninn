# Desk

DESK-01 is a local night desk on this checkout. It reads the synthetic ledger and the allocation module. It does not fetch a price, invent an FX rate, recommend a transaction, or forecast a return.

## Deferred hosted target

The hosted constitution target remains FastAPI, React, and PostgreSQL. That target stays deferred because this milestone cannot install dependencies. No FastAPI app, React bundle, PostgreSQL database, npm package, or CDN asset is added. The desk uses the Python standard library and one local script.

## Average cost

`Ledger.performance(on_date)` is specified in `docs/ACCOUNTING_LEDGER.md`. The desk shows open average cost, realized gain, unrealized gain, reporting-currency dividend income, and the residual. When the valuation is incomplete, the page says the residual is unknown. A missing unrealized gain stays unknown. It is not shown as zero.

The residual is an accounting identity. It is not a return, not an annualized figure, and not a forecast.

## Allocation

`src/huginn_muninn/allocation.py` compares one valuation with Decimal weights supplied by the caller. The fixture stores the weights in `fixtures/synthetic_portfolio.json`. The module does not hardcode them.

The weights must sum to `Decimal('1')`. Otherwise the status is `invalid_targets` and there are no gap amounts. If the valuation is not complete, the status is `incomplete`, gap amounts are absent, and the valuation reasons are retained. A missing holding is not treated as a zero weight.

When the valuation is complete and the targets are valid, each configured key gets the current reporting amount, or zero only when the books have no row for that key. Current weight is that amount divided by the known subtotal in the local 28-digit context. The illustrative amount is the target weight times the known subtotal, minus the current amount. Every such row has kind `arithmetic_gap` and recommendation `None`. A key with no target is `untargeted` and has no illustrative amount.

The result carries this sentence exactly: "This is the arithmetic difference from the configured target. It is not an investment recommendation."

Fixture targets are cash:NOK 0.20, northline 0.55, and harbor 0.25. At 2026-03-31 the illustrative amounts are -10063.50, 4752.875, and 5310.625. At 2026-03-10 the same targets produce status `incomplete` and no illustrative amounts.

The same result returns listing-currency exposure from qualified valuation lines: NOK cash plus NOK-listed positions, and USD-listed positions at their reporting amount. The label is listing-currency exposure. It is not look-through, and it has no target.

## Pages

`python scripts/serve_prototype.py` still binds `127.0.0.1:8765`.

- `GET /` is the desk for the latest stored date, or for `?date=YYYY-MM-DD`.
- `GET /ledger` is the previous paper home.
- `GET /transactions`, `GET /history`, `GET /valuation`, `GET /reconcile`, `GET /chart`, and `POST /reset` still work. `POST /reset` returns the desk.
- `GET /api/desk?date=YYYY-MM-DD` returns JSON from `json.dumps`. Decimal amounts are strings. The known subtotal equals `Ledger.value` for that date. A missing reporting amount is `null`, not `"0"`. An invalid date returns status 400.
- `GET /conversation` shows a text form and a still waveform.
- `POST /conversation` appends a deterministic reply. It does not call a model.

The desk links to the journal pages. The HTML for `GET /` contains the live cash and known subtotal because the server built them from the engine, along with the words synthetic and the phrase not a recommendation. A script may refresh those figures from `/api/desk`; this page does not need one, because the server already wrote them.

The waveform script is `static/desk/waveform.js`, served only from `static/desk`. A path that escapes that directory is rejected. The script does not contain the fixture totals as literals.

## Conversation and waveform

Replies are chosen from the loaded books:

- Text that mentions recommend, should I, buy, or sell as advice is refused. The desk does not recommend a transaction. If a complete allocation exists, the reply repeats the arithmetic-gap sentence. It does not name a trade to place.
- A question about value or total replies with the engine's known subtotal and complete flag.
- A question about allocation or rebalance replies with the illustrative amounts, or with the incomplete status, and the non-recommendation sentence.
- Any other question says the desk can explain the loaded books, the valuation, and the arithmetic gaps, and that the question was not one of those.

The waveform bars stay still. The page says "No audio input. Speech recognition is not implemented." The button labeled "Use microphone" may call `getUserMedia` and `AnalyserNode`, and only then move the bars from measured levels. If permission is denied or the API is missing, the bars stay still and the same sentence remains. The script does not animate fake speech, and it does not say that speech was recognized or that a voice model replied. Speech synthesis is not implemented. There is no live conversation model.

## What the desk shows

- the qualified known subtotal and whether it is complete
- cash and holdings, with listing currency on the holdings
- allocation weights, percentage-point gaps, and illustrative amounts only when the status is complete
- the exact non-recommendation sentence
- listing-currency exposure
- performance components and the residual, or a statement that the residual is unknown when the valuation is incomplete
- provenance for the prices and rates the valuation actually cites
- an evidence panel listing those citations
- empty intelligence slots: "No competing evidence is loaded. No interpretation is offered." "Confidence is not assessed." "Risk is not assessed. No risk model is loaded." "No forecast is computed."
- the historical known-subtotal chart from stored dates only, with incomplete points in the break color and no interpolated dates

## Visual direction

The desk is a night workspace for reading a ledger. The field is `#14181f`, the ink `#e7e2d6`, the dim text `#8d97a3`, qualified figures `#d7b58a`, breaks `#d07a6a`, and rules `#2a3140`. The product name and the one total use Palatino Linotype, Palatino, Georgia. Dense reading uses Segoe UI, Candara, sans-serif. Figures use Cascadia Mono, Consolas, monospace. No font is downloaded. Text is left aligned. Figures are tabular and right aligned. At 360px the columns stack. Focus is visible. `prefers-reduced-motion` stops animation.

## Review state

Independent review on 2026-10-11 approved DESK-01. Reviewer `a9e2c765-84f1-45a7-8305-122f1f424958`. The parent sandbox discovered 89 tests, exit code 0. This note is not production financial readiness.
