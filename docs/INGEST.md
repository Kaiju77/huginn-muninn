# Ingest

INGEST-01 reads public series into the evidence store. The synthetic ledger rate stays 10.25. Independent review on 2026-10-11 approved that layer. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30`. INGEST-02 adds Norges Bank EUR/NOK, the verified policy rate, and the NOWA rate to the same explicit refresh. Independent review on 2026-10-11 approved INGEST-02. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff`. This note is not a recommendation and not production financial readiness.

## Allowlist

The client opens a socket only for these hosts:

- `data.norges-bank.no`
- `data-api.ecb.europa.eu`
- `data.ssb.no`
- `data.sec.gov`

Any other host, including `api.stlouisfed.org` and `data.stlouisfed.org`, fails before a socket is opened. The reason is `not_allowlisted`. FRED is not on the allowlist.

## Timeout, interval, and retries

The timeout is 15 seconds. The minimum interval is 2 seconds per host. At most 2 retries, and only for a timeout or HTTP 429, 500, 502, 503, or 504. Other 4xx responses are not retried.

A body larger than 1000000 bytes is rejected in the client before parsing. The reason is `body_too_large`.

The raw body, URL, status, and retrieval timestamp are cached under a caller-supplied directory. Tests use a temporary directory. The runtime directory is `var/ingest-cache/`, which `var/` already gitignores.

Errors are structured results: `not_allowlisted`, `timeout`, `http_status`, `parse_error`, `configuration_required`, and `body_too_large`. The package provides an async fetch and a sync wrapper. Unittest injects a fake transport. `urllib` is used only by the live transport, and only when a caller explicitly refreshes. `GET /evidence` does not fetch. Importing the package does not fetch.

## Identity

A repeat is a duplicate only when `observation_id`, `source_id`, subject, unit, value, `observation_time`, `retrieval_time`, provenance, and quality flags all match. The same `observation_id` with any other field different, including the same Decimal value and a different `observation_time`, is a conflict. Both observations stay visible. The later row is not dropped, and the first row is not overwritten. The conflict record shows both observation dates, not only the amounts. Neither value is copied into the ledger.

`refresh.json` merges a later explicit refresh with the rows already stored. A new row with the same observation id and the same source, subject, unit, value, `observation_time`, `retrieval_time`, provenance, and quality stays one stored row. The same observation id with any different field keeps both rows and appends one revision record with the id, both values, and both retrieval times. An observation id that is absent from the new batch stays stored. Identical refreshes do not add another revision record. If the stored observation count would exceed 500, the oldest observation dates that are not in the new batch are dropped until the count is 500. The desk lists revision records when they exist.

## What was connected

Norges Bank and the ECB are connected. `live_fetch` is true for `norges-bank-open-data` and `ecb-sdw`.

An explicit refresh requests five series, and only when the caller passes a transport or `explicit_live`:

- Norges Bank USD/NOK is `https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv` with the posted `startPeriod` and `endPeriod`. The value is NOK per 1 USD, parsed with `Decimal` from the body. The observation id is `nb-exr-USD-NOK-{TIME_PERIOD}`. Provenance quotes Norges Bank open data and the URL. The COLLECTION column can mention an ECB concertation time. That column does not relabel the series as an ECB rate.
- Norges Bank EUR/NOK uses the same parser and the URL `https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=csv` with the posted window. The value is NOK per 1 EUR. The observation id is `nb-exr-EUR-NOK-{TIME_PERIOD}`. Provenance quotes Norges Bank open data and the URL. It is not relabeled as an ECB series. The captured rows are 2026-10-08 value 10.717 and 2026-10-09 value 10.7155. Those two amounts were retrieved on 2026-10-11.
- The verified Norges Bank policy-rate key is `IR/B.KPRA.SD.R`. The URL is `https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R?format=csv` with the posted window. `IR/K.POL.NOK` returned HTTP 404 on 2026-10-11. That rejected key stays documented and is not requested. The semicolon CSV requires TIME_PERIOD, OBS_VALUE, INSTRUMENT_TYPE KPRA, TENOR SD, and UNIT_MEASURE R. If a row has another tenor, including OL overnight lending, the result is `parse_error` and no policy-rate row from that body is stored. The observation id is `nb-ir-KPRA-SD-{TIME_PERIOD}`. The subject is policy-rate. The unit is percent. OBS_VALUE text is stored unchanged. A captured body for 2026-10-06 through 2026-10-08 has the value text 4.5.
- The NOWA rate key is `SHORT_RATES/B.NOWA.ON.R`. The URL is `https://data.norges-bank.no/api/data/SHORT_RATES/B.NOWA.ON.R?format=csv`. The parser requires INSTRUMENT_TYPE NOWA, TENOR ON, and UNIT_MEASURE R. Volume, transaction, and index rows are not stored. The observation id is `nb-short-NOWA-ON-R-{TIME_PERIOD}`. The subject is nowa. The unit is percent. OBS_VALUE text is stored unchanged. A captured body for 2026-10-06 through 2026-10-08 has the value text 4.50.

The ECB series is `https://data-api.ecb.europa.eu/service/data/EXR/D.NOK.EUR.SP00.A?format=csvdata`. The unit is NOK per 1 EUR. The observation id is `ecb-exr-NOK-EUR-{TIME_PERIOD}`. `OBS_VALUE` text is passed to `Decimal` unchanged. Provenance includes the sentence "Source: ECB statistics." The reuse policy allows free reuse when the source is quoted and the figures are not modified. `license_status` is `verified_free_reuse_with_citation`. The policy page is `https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html`.

Statistics Norway is prepared, and `live_fetch` stays false. The license is CC BY 4.0. An extract is limited to 800000 cells and 30 queries a minute. The figures are statistics, not security prices. The adapter can parse a recorded one-row fixture. Refresh does not call it: a bounded live query was not locked in this increment. Table 03013 is discontinued through 2025M12. Do not call it. A current table id is still an open human decision.

SEC EDGAR is prepared for `data.sec.gov`. It refuses to fetch until a User-Agent contact string is configured. The reason is `configuration_required`. This increment does not invent an email address and does not perform a live EDGAR request. Fair access remains 10 requests per second and a declared user agent. Filings are not prices.

FRED stays blocked. `live_fetch` is false. `blocked_reason` is `api_key_and_terms`.

`social-unverified` stays excluded.

Quality is `live_retrieval` when the body came from the live transport, and `recorded_fixture` when it came from a fixture file. The synthetic 10.25 fixture stays labeled synthetic. It is not drawn as a Norges Bank point. The USD/NOK chart uses stored observations only and does not interpolate missing dates. NOWA is not drawn on that chart. The policy-rate chart uses the same rules for stored policy-rate points. The synthetic 4.50 policy fixture is not drawn as a live Norges Bank point.

## Refresh is manual

`POST /evidence/refresh` runs one explicit refresh for the five series above for the posted date window. Refresh is manual. It is not a scheduler, a background loop, or an agent. Tests call `refresh_public` with the fake transport and do not bind a socket. The fake transport chooses each body from the URL path.

`due_status` looks only at stored observations and an as-of date. A connected source is current when it has one non-synthetic observation whose freshness is fresh. Otherwise it is due. The evidence page prints each connected source as current or due. The function does not fetch and does not start a loop. Synthetic fixture rows do not make a source current.

On 2026-10-11 the parent posted `start_period=2026-10-01` and `end_period=2026-10-09` to the local desk during INGEST-01. The page recorded last refresh `2026-10-11T08:03:34+00:00`. Against date 2026-10-11, `nb-exr-USD-NOK-2026-10-09` is 9.5623 NOK per 1 USD, retrieved 2026-10-11, quality `live_retrieval`, freshness fresh. `ecb-exr-NOK-EUR-2026-10-09` is 10.7155 NOK per 1 EUR, with the same retrieval date, quality, and freshness. The synthetic ledger rate stayed 10.25. That call is a demonstration, not an offline test result. It predates the five-series refresh.

The offline sandbox used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, network disabled, checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 123 tests, 123 passed, exit code 0. A later parent rerun, after the live-versus-synthetic sentence, also discovered 123 tests, exit code 0. Those runs did not call the network. The reviewer did not rerun the suite. Those receipts belong to INGEST-01.

The INGEST-02 implementer sandbox used the same image, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 130 tests, 130 passed, exit code 0. An earlier run exited 1 because the evidence page string was missing a concatenation operator. That operator was added before the passing run. The parent rerun discovered 130 tests, exit code 0, and did not call the network. The reviewer did not rerun the suite.
