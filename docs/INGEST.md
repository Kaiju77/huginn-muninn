# Ingest

INGEST-01 reads two public series into the evidence store. The synthetic ledger rate stays 10.25. Independent review on 2026-10-11 approved the layer. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30`. This note is not a recommendation and not production financial readiness.

## Allowlist

The client opens a socket only for these hosts:

- `data.norges-bank.no`
- `data-api.ecb.europa.eu`
- `data.ssb.no`
- `data.sec.gov`

Any other host, including `api.stlouisfed.org` and `data.stlouisfed.org`, fails before a socket is opened. The reason is `not_allowlisted`. FRED is not on the allowlist.

## Timeout, interval, and retries

The timeout is 15 seconds. The minimum interval is 2 seconds per host. At most 2 retries, and only for a timeout or HTTP 429, 500, 502, 503, or 504. Other 4xx responses are not retried.

The raw body, URL, status, and retrieval timestamp are cached under a caller-supplied directory. Tests use a temporary directory. The runtime directory is `var/ingest-cache/`, which `var/` already gitignores.

Errors are structured results: `not_allowlisted`, `timeout`, `http_status`, `parse_error`, and `configuration_required`. The package provides an async fetch and a sync wrapper. Unittest injects a fake transport. `urllib` is used only by the live transport, and only when a caller explicitly refreshes. `GET /evidence` does not fetch. Importing the package does not fetch.

## Identity

A repeat is a duplicate only when `observation_id`, `source_id`, subject, unit, value, `observation_time`, `retrieval_time`, provenance, and quality flags all match. The same `observation_id` with any other field different, including the same Decimal value and a different `observation_time`, is a conflict. Both observations stay visible. The later row is not dropped, and the first row is not overwritten. The conflict record shows both observation dates, not only the amounts. Neither value is copied into the ledger.

## What was connected

Norges Bank and the ECB are connected. `live_fetch` is true for `norges-bank-open-data` and `ecb-sdw`.

Norges Bank USD/NOK is `https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv` with an explicit `startPeriod` and `endPeriod`. The value is NOK per 1 USD, parsed with `Decimal` from the body. The observation id is `nb-exr-USD-NOK-{TIME_PERIOD}`. Provenance quotes Norges Bank open data and the URL. The COLLECTION column can mention an ECB concertation time. That column does not relabel the series as an ECB rate. The same parser accepts `EXR/B.EUR.NOK.SP` when a body is supplied. Refresh does not request that series.

`IR/K.POL.NOK` returned HTTP 404 on 2026-10-11. No replacement policy-rate key is invented, and refresh does not request that key.

The ECB series is `https://data-api.ecb.europa.eu/service/data/EXR/D.NOK.EUR.SP00.A?format=csvdata`. The unit is NOK per 1 EUR. The observation id is `ecb-exr-NOK-EUR-{TIME_PERIOD}`. `OBS_VALUE` text is passed to `Decimal` unchanged. Provenance includes the sentence "Source: ECB statistics." The reuse policy allows free reuse when the source is quoted and the figures are not modified. `license_status` is `verified_free_reuse_with_citation`. The policy page is `https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html`.

Statistics Norway is prepared, and `live_fetch` stays false. The license is CC BY 4.0. An extract is limited to 800000 cells and 30 queries a minute. The figures are statistics, not security prices. The adapter can parse a recorded one-row fixture. Refresh does not call it: a bounded live query was not locked in this increment.

SEC EDGAR is prepared for `data.sec.gov`. It refuses to fetch until a User-Agent contact string is configured. The reason is `configuration_required`. This increment does not invent an email address and does not perform a live EDGAR request. Fair access remains 10 requests per second and a declared user agent. Filings are not prices.

FRED stays blocked. `live_fetch` is false. `blocked_reason` is `api_key_and_terms`.

`social-unverified` stays excluded.

Quality is `live_retrieval` when the body came from the live transport, and `recorded_fixture` when it came from a fixture file. The synthetic 10.25 fixture stays labeled synthetic. It is not drawn as a Norges Bank point. The USD/NOK chart uses stored observations only and does not interpolate missing dates.

## Refresh is manual

`POST /evidence/refresh` runs one explicit refresh for Norges Bank USD/NOK and ECB NOK/EUR for the posted date window. Refresh is manual. It is not a scheduler, a background loop, or an agent. Tests call `refresh_public` with the fake transport and do not bind a socket.

On 2026-10-11 the parent posted `start_period=2026-10-01` and `end_period=2026-10-09` to the local desk. The page recorded last refresh `2026-10-11T08:03:34+00:00`. Against date 2026-10-11, `nb-exr-USD-NOK-2026-10-09` is 9.5623 NOK per 1 USD, retrieved 2026-10-11, quality `live_retrieval`, freshness fresh. `ecb-exr-NOK-EUR-2026-10-09` is 10.7155 NOK per 1 EUR, with the same retrieval date, quality, and freshness. The synthetic ledger rate stayed 10.25. That call is a demonstration, not an offline test result.

The offline sandbox used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, network disabled, checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 123 tests, 123 passed, exit code 0. A later parent rerun, after the live-versus-synthetic sentence, also discovered 123 tests, exit code 0. Those runs did not call the network. The reviewer did not rerun the suite.
