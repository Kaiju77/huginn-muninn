# Local prototype

PROTOTYPE-01 is a standard-library paper ledger on this checkout. It loads synthetic inputs and calls `Ledger`. Posting, valuation, and reconciliation stay in `src/huginn_muninn/ledger.py`.

## Decision record

The hosted constitution target remains FastAPI, React, and PostgreSQL. That target is deferred for this milestone because dependencies cannot be installed. This interface uses the Python standard library only. No FastAPI app, React bundle, PostgreSQL database, pip dependency, or CDN asset is added.

## Run

From the checkout root:

```text
python scripts/serve_prototype.py
```

The process binds `127.0.0.1` port `8765` and prints `http://127.0.0.1:8765/`. A non-loopback bind is refused before a socket opens. `localhost` is normalized to `127.0.0.1`. `::1` is accepted as loopback. There is no authentication: the figures are synthetic and the socket is local.

A bare port argument or `--port` changes the port. `--bind` selects the loopback address.

## Data

`fixtures/synthetic_portfolio.json` is the committed reset source. Amounts, quantities, fees, prices, and rates are JSON strings. The loader constructs `Decimal` values from those strings and rejects JSON numbers, so a float cannot be coerced into the journal.

`var/synthetic-book.json` is the runtime overlay. `var/` and `__pycache__/` are gitignored. When the overlay file exists, the process starts from it. Otherwise it starts from the fixture. After a successful or rejected submission, the overlay is rewritten from the full input set: accounts, instruments, events including rejected events, prices, rates, and statements. A later start replays that file through `Ledger.record`, `add_price`, and `add_rate`.

`POST /reset` deletes only that overlay file and reloads the fixture.

Reporting currency is NOK. The account is `brokerage`. The instruments are fictional: Northline Equity Fund, listed in NOK, and Harbor Global Fund, listed in USD. The pages state that the figures are synthetic and that the page is not a recommendation.

## Pages

Pages are server-rendered. Forms use `application/x-www-form-urlencoded`. No JavaScript is required.

- `GET /` shows the latest book date in the loaded inputs, cash, holdings, and whether the latest valuation is complete.
- `GET /transactions` lists every retained event, accepted or rejected, with reasons.
- `GET /transactions/new` shows the deposit, withdrawal, buy, sell, and dividend form.
- `POST /transactions` parses amount fields with `Decimal(str)` and records the event through the ledger. The response redisplays the posting reasons. A rejected event leaves the books unchanged.
- `GET /history?date=YYYY-MM-DD` shows books on that date. An invalid date shows the ledger error and returns status 400.
- `GET /valuation?date=YYYY-MM-DD` shows each line's source amount, reporting amount, price id, rate id, and reasons. A missing reporting amount is blank. The known subtotal is labeled known subtotal. An incomplete valuation says the total is not complete and names the excluded lines.
- `GET /reconcile` lists the stored statements and their results.
- `POST /reconcile` submits one synthetic statement through `Ledger.reconcile` and shows the breaks. A new statement id is appended to the saved statements.
- `GET /chart` returns one inline SVG. Points are only dates that exist on accepted events, accepted prices, or accepted rates. Each point is that date's known subtotal and complete flag from `Ledger.value`. Dates are not interpolated. Incomplete points are squares in the break color. Complete points are circles in the qualified color. When any plotted date is incomplete, the caption says known subtotal.

The visual is a paper ledger. Prose is left aligned. The right-hand column is a running figure column, tabular and right aligned. Table cells stay on one line, and a wide table scrolls inside the page. Palette: paper `#E7EEF2`, ink `#14202B`, qualified amount `#0E6B4F`, break `#9B2C2C`, rule `#8AA0B2`. Type is Palatino Linotype, Palatino, Iowan Old Style, Georgia for prose, and Consolas, Cascadia Mono, monospace for figures. No font is downloaded.

## Decimal and scope

Valuation precision is in `docs/DECIMAL_RULES.md`. The application does not fetch market data, open a network connection, or add recommendations, forecasts, tax lots, or cost basis.
