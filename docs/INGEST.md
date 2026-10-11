# Ingest

INGEST-01 reads public series into the evidence store. The synthetic ledger rate stays 10.25. Independent review on 2026-10-11 approved that layer. Reviewer `d9738456-8e9c-486d-9b05-cab7ecd21d30`. INGEST-02 adds Norges Bank EUR/NOK, the verified policy rate, and the NOWA rate to the same explicit refresh. Independent review on 2026-10-11 approved INGEST-02. Reviewer `b892e214-6e19-40b9-a2e4-bf70978f63ff`. INGEST-03 adds a NOWA chart, a two-source EUR/NOK difference, and one Statistics Norway CPI cell. Independent review on 2026-10-11 approved INGEST-03. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5`. INGEST-04 adds the monthly CPI sentence and the stored-series inventory on the evidence page. Independent review on 2026-10-11 approved INGEST-04. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594`. This note is not a recommendation and not production financial readiness.

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

Norges Bank, the ECB, and Statistics Norway are connected. `live_fetch` is true for `norges-bank-open-data`, `ecb-sdw`, and `ssb-statbank`. Statistics Norway is connected for one cell. Other SSB tables remain unconnected.

An explicit refresh requests six URLs, and only when the caller passes a transport or `explicit_live`. The first five use the posted window:

- Norges Bank USD/NOK is `https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv` with the posted `startPeriod` and `endPeriod`. The value is NOK per 1 USD, parsed with `Decimal` from the body. The observation id is `nb-exr-USD-NOK-{TIME_PERIOD}`. Provenance quotes Norges Bank open data and the URL. The COLLECTION column can mention an ECB concertation time. That column does not relabel the series as an ECB rate.
- Norges Bank EUR/NOK uses the same parser and the URL `https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=csv` with the posted window. The value is NOK per 1 EUR. The observation id is `nb-exr-EUR-NOK-{TIME_PERIOD}`. Provenance quotes Norges Bank open data and the URL. It is not relabeled as an ECB series. The captured rows are 2026-10-08 value 10.717 and 2026-10-09 value 10.7155. Those two amounts were retrieved on 2026-10-11.
- The verified Norges Bank policy-rate key is `IR/B.KPRA.SD.R`. The URL is `https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R?format=csv` with the posted window. `IR/K.POL.NOK` returned HTTP 404 on 2026-10-11. That rejected key stays documented and is not requested. The semicolon CSV requires TIME_PERIOD, OBS_VALUE, INSTRUMENT_TYPE KPRA, TENOR SD, and UNIT_MEASURE R. If a row has another tenor, including OL overnight lending, the result is `parse_error` and no policy-rate row from that body is stored. The observation id is `nb-ir-KPRA-SD-{TIME_PERIOD}`. The subject is policy-rate. The unit is percent. OBS_VALUE text is stored unchanged. A captured body for 2026-10-06 through 2026-10-08 has the value text 4.5.
- The NOWA rate key is `SHORT_RATES/B.NOWA.ON.R`. The URL is `https://data.norges-bank.no/api/data/SHORT_RATES/B.NOWA.ON.R?format=csv`. The parser requires INSTRUMENT_TYPE NOWA, TENOR ON, and UNIT_MEASURE R. Volume, transaction, and index rows are not stored. The observation id is `nb-short-NOWA-ON-R-{TIME_PERIOD}`. The subject is nowa. The unit is percent. OBS_VALUE text is stored unchanged. A captured body for 2026-10-06 through 2026-10-08 has the value text 4.50.

The ECB series is `https://data-api.ecb.europa.eu/service/data/EXR/D.NOK.EUR.SP00.A?format=csvdata`. The unit is NOK per 1 EUR. The observation id is `ecb-exr-NOK-EUR-{TIME_PERIOD}`. `OBS_VALUE` text is passed to `Decimal` unchanged. Provenance includes the sentence "Source: ECB statistics." The reuse policy allows free reuse when the source is quoted and the figures are not modified. `license_status` is `verified_free_reuse_with_citation`. The policy page is `https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html`.

Statistics Norway `ssb-statbank` is connected for one cell. The license remains CC BY 4.0. An extract is limited to 800000 cells and 30 queries a minute. The figures are statistics, not security prices. Table 03013 is discontinued through 2025M12. Do not call it. Table 14700 replaces discontinued table 03013. The only Statistics Norway request, added after the five series above, is `https://data.ssb.no/api/pxwebapi/v2/tables/14700/data?lang=en&valueCodes[Tid]=2026M07&valueCodes[VareTjenesteGrp]=00&valueCodes[ContentsCode]=KpiIndMnd`. The posted window does not change that URL. The parser uses `json.loads(text, parse_float=str)`. It requires exactly one value, group 00 labeled Total, contents KpiIndMnd, and time 2026M07. The stored value text is 103.8. The number is not passed through float. The observation id is `ssb-cpi-total-2026M07`. The subject is `cpi-total`. The unit is `index 2025=100`. `observation_time` is 2026-07-01, the first day of month 2026M07. Against 2026-10-11 and a 7-day window that row is stale. When the observation is visible, the evidence page includes: "The CPI date is the first day of 2026M07. Stale in October means the monthly index is older than 7 days. It is not a failed daily refresh." The freshness rule is unchanged. The page does not mark the row fresh. The evidence page also lists each stored subject once. The line shows the source id, the latest observation date among visible rows for that subject, and the value on that latest date. If two rows share the latest date, the line shows both values and says the date has more than one row. The inventory is computed from stored rows only. It does not recommend, forecast, or write the ledger. Provenance cites Statistics Norway, CC BY 4.0, table 14700, and says this is a price index, not a security price. A body with more than one value is `parse_error` and stores nothing. Other SSB tables remain unconnected. Before INGEST-03, a bounded live query was not locked. The recorded one-row fixture parser remains for that local file and is not this request.

SEC EDGAR is prepared for `data.sec.gov`. It refuses to fetch until a User-Agent contact string is configured. The reason is `configuration_required`. This increment does not invent an email address and does not perform a live EDGAR request. Fair access remains 10 requests per second and a declared user agent. Filings are not prices.

FRED stays blocked. `live_fetch` is false. `blocked_reason` is `api_key_and_terms`.

`social-unverified` stays excluded.

Quality is `live_retrieval` when the body came from the live transport, and `recorded_fixture` when it came from a fixture file. The synthetic 10.25 fixture stays labeled synthetic. It is not drawn as a Norges Bank point. The USD/NOK chart uses stored observations only and does not interpolate missing dates. NOWA is not drawn on that chart. The policy-rate chart uses the same rules for stored policy-rate points. The synthetic 4.50 policy fixture is not drawn as a live Norges Bank point. The NOWA chart is an inline SVG with id `nowa-ingested`. It uses the same marker rules for stored observations whose subject is nowa, whose source is `norges-bank-open-data`, and whose quality is `live_retrieval` or `recorded_fixture`. Missing dates are not interpolated. The synthetic policy fixture, USD/NOK points, and EUR/NOK points are not drawn on it.

For each observation date that has both `nb-exr-EUR-NOK-{date}` and `ecb-exr-NOK-EUR-{date}`, the evidence page shows both values and the arithmetic difference Norges Bank minus ECB. The difference is computed with Decimal and rendered with `format(value, 'f')`. The captured fixtures are 10.717 and 10.7155 on both 2026-10-08 and 2026-10-09, so those differences are 0. Decimal subtraction of 10.717 keeps a scale of three, so the raw difference formats as 0.000. When the Decimal difference equals zero, the page renders `format(Decimal(0), 'f')`, which is 0. A non-zero difference is `format(difference, 'f')`. The page says: "This difference is not a recommendation and is not copied into the ledger." If only one side exists, the pair is incomplete and no difference is printed. Neither rate is inverted.

## Refresh is manual

`POST /evidence/refresh` runs one explicit refresh for the six requests above. The five exchange and rate series use the posted date window. The sixth request is the fixed Statistics Norway cell. Refresh is manual. It is not a scheduler, a background loop, or an agent. Tests call `refresh_public` with the fake transport and do not bind a socket. The fake transport chooses each body from the URL path. It returns `fixtures/http/ssb-cpi-total-2026m07.json` only for the table 14700 URL above.

`due_status` looks only at stored observations and an as-of date. A connected source is current when it has one non-synthetic observation whose freshness is fresh. Otherwise it is due. The evidence page prints each connected source as current or due. The function does not fetch and does not start a loop. Synthetic fixture rows do not make a source current.

On 2026-10-11 the parent posted `start_period=2026-10-01` and `end_period=2026-10-09` to the local desk during INGEST-01. The page recorded last refresh `2026-10-11T08:03:34+00:00`. Against date 2026-10-11, `nb-exr-USD-NOK-2026-10-09` is 9.5623 NOK per 1 USD, retrieved 2026-10-11, quality `live_retrieval`, freshness fresh. `ecb-exr-NOK-EUR-2026-10-09` is 10.7155 NOK per 1 EUR, with the same retrieval date, quality, and freshness. The synthetic ledger rate stayed 10.25. That call is a demonstration, not an offline test result. It predates the five-series refresh.

The offline sandbox used image `sha256:1ec077c900d954b540018818f0dea239d7c3ffcf7638f49e090cbf14832d061f`, network disabled, checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 123 tests, 123 passed, exit code 0. A later parent rerun, after the live-versus-synthetic sentence, also discovered 123 tests, exit code 0. Those runs did not call the network. The reviewer did not rerun the suite. Those receipts belong to INGEST-01.

The INGEST-02 implementer sandbox used the same image, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 130 tests, 130 passed, exit code 0. An earlier run exited 1 because the evidence page string was missing a concatenation operator. That operator was added before the passing run. The parent rerun discovered 130 tests, exit code 0, and did not call the network. The reviewer did not rerun the suite.

The INGEST-03 implementer sandbox used the same image, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 132 tests, 132 passed, exit code 0. Two earlier runs exited 1. The first failed because the CPI URL was split across string literals. The second failed because the last stored row was the CPI observation, and then because an equal-rate difference rendered as 0.000. Those were corrected before the passing run. That run did not call the network. Independent review on 2026-10-11 approved INGEST-03. Reviewer `b30fc8b7-9c31-4500-837a-3243f3be9cc5`.

The INGEST-04 implementer sandbox used the same image, with the network disabled and the checkout copied into container scratch. `python -m unittest discover -s tests -v` discovered 137 tests, 137 passed, exit code 0. That run did not call the network. Independent review on 2026-10-11 approved INGEST-04. Reviewer `20fd508e-2a5f-49a3-a4fb-f8c2d0ce9594`. The reviewer did not rerun the suite.
