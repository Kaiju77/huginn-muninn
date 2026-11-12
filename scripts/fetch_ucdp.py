#!/usr/bin/env python3
"""Fetch UCDP GED events for Middle East countries into data/ucdp/ged_mideast.csv.

    python scripts/fetch_ucdp.py                 # GED 26.1, all countries
    UCDP_VERSION=26.1 UCDP_TOKEN=... python scripts/fetch_ucdp.py

Runs in GitHub Actions (this sandbox cannot reach UCDP). The token is read
from the environment variable UCDP_TOKEN and sent only as an HTTP header;
it is never printed, logged or put in a URL. On any failure the old CSV is
kept and the exit code is non-zero.

What the UCDP API documentation says (read 2026-11-12)
------------------------------------------------------
Sources:
- https://ucdp.uu.se/apidocs/  (official API documentation)
- https://ucdp.uu.se/downloads/ged/ged261.pdf  (GED 26.1 codebook)
- https://apis.io/apis/uppsala/uppsala-gedevents-api/  (OpenAPI listing)
- https://ucdptestapi.pcr.uu.se/Help  (API help page of the test server)

CONFIRMED in the official docs:
- URL pattern ``https://ucdpapi.pcr.uu.se/api/<resource>/<version>``; GED
  resource is ``gedevents``. Example in the docs:
  ``https://ucdpapi.pcr.uu.se/api/gedevents/26.1?pagesize=1&page=295``.
- Latest final GED version listed: ``26.1`` (codebook: coverage
  1989-01-01 to 2025-12-31, extracted 2026-03-30). Monthly candidate
  releases (e.g. ``26.0.9``) use the same resource; not fetched here.
- Paging: query parameters ``pagesize`` and ``page``. Response JSON keys:
  ``TotalCount``, ``TotalPages``, ``PreviousPageUrl``, ``NextPageUrl``,
  ``Result`` (list of events).
- Filters: ``Country`` takes Gleditsch-Ward codes, several separated by
  commas (docs example ``Country=90,91,92``). ``StartDate``/``EndDate``
  (YYYY-MM-DD) filter on ``date_end``. ``TypeOfViolence`` also exists.
- An access token is now REQUIRED (requested by e-mail from UCDP), sent in
  the HTTP header ``x-ucdp-access-token``. Quota: 5,000 requests a day,
  errors included.
- GED field names used here: ``id``, ``date_start``, ``date_end``,
  ``date_prec`` (1 exact day .. 5 under a year), ``country``,
  ``country_id`` (Gleditsch-Ward), ``region`` (Africa, Americas, Asia,
  Europe, Middle East), ``type_of_violence`` (1 state-based, 2 non-state,
  3 one-sided), ``best`` (best estimate of total fatalities). The codebook
  says to use ``id`` (not ``relid``) as the persistent event id, and that
  missing values come back as null or empty strings.

UNCONFIRMED (configurable):
- Maximum ``pagesize``: not stated. Default 1000 (``--pagesize``).
- Whether ``page`` is 0- or 1-based: not stated. The fetcher follows the
  server's ``NextPageUrl`` (host-checked) and does not count pages itself.
- Whether ``Country`` and ``TypeOfViolence`` filters combine as AND: assumed;
  every returned row is checked against the requested countries anyway.
- Palestine: there is no Gleditsch-Ward code; GED is expected to file Gaza
  and West Bank events under Israel (666). Check ``country`` in real data.
- Version is configurable with ``--version`` or env ``UCDP_VERSION``.
"""

import argparse
import csv
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.ucdp_events import COUNTRIES, GedRow  # noqa: E402

API_HOST = 'ucdpapi.pcr.uu.se'
API_BASE = f'https://{API_HOST}/api/gedevents/'
DEFAULT_VERSION = '26.1'
DEFAULT_PAGESIZE = 1000
TOKEN_HEADER = 'x-ucdp-access-token'
OUT = ROOT / 'data' / 'ucdp' / 'ged_mideast.csv'
MIN_ROWS = 1000
MAX_PAGES = 2000
# Iran, Iraq, Israel (incl. Palestine, see above), Lebanon, Syria, Yemen
# (and South Yemen before 1990), Saudi Arabia, Kuwait, UAE, Qatar, Bahrain,
# Oman, Libya, Jordan.
MIDEAST_COUNTRY_IDS = tuple(sorted(COUNTRIES))
CSV_COLUMNS = GedRow._fields


def first_url(version, pagesize, country_ids=MIDEAST_COUNTRY_IDS):
    params = [('pagesize', str(pagesize)),
              ('Country', ','.join(str(c) for c in country_ids))]
    return (API_BASE + urllib.parse.quote(version, safe='.') + '?'
            + urllib.parse.urlencode(params, safe=','))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: urllib would forward the token header to any host,
    even over plain http (review round 9)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'redirect refused', headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_get(url, token, retries=3, opener=None):
    """GET with the token in a header, no redirects. Errors never contain the token."""
    opener = opener or _OPENER
    headers = {'Accept': 'application/json', 'User-Agent': 'huginn-muninn-fetch'}
    if token:
        headers[TOKEN_HEADER] = token
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with opener.open(request, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                raise RuntimeError(f'HTTP {err.code}: access denied (check UCDP_TOKEN)') from None
            if 300 <= err.code < 400:
                raise RuntimeError(f'HTTP {err.code}: redirect refused') from None
            if attempt == retries - 1:
                raise RuntimeError(f'HTTP {err.code}') from None
        except (urllib.error.URLError, TimeoutError, http.client.HTTPException, OSError) as err:
            # HTTPException covers IncompleteRead (a truncated body).
            if attempt == retries - 1:
                raise RuntimeError(f'request failed: {type(err).__name__}') from None
        time.sleep(2 ** attempt * 5)
    raise AssertionError('unreachable')


def _int(item, key, idx):
    value = item.get(key)
    if value is None or value == '':
        raise ValueError(f'row {idx}: {key} is missing')
    if isinstance(value, bool):
        raise ValueError(f'row {idx}: {key} is not an integer')
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not (text.isdigit() or (text.startswith('-') and text[1:].isdigit())):
        raise ValueError(f'row {idx}: {key} is not an integer')
    return int(text)


def _date(item, key, idx):
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f'row {idx}: {key} is missing')
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(f'row {idx}: {key} is not YYYY-MM-DD') from None


def parse_row(item, idx, today, country_ids):
    if not isinstance(item, dict):
        raise ValueError(f'row {idx}: not an object')
    event_id = item.get('id')
    if event_id is None or str(event_id).strip() == '':
        raise ValueError(f'row {idx}: id is missing')
    start, end = _date(item, 'date_start', idx), _date(item, 'date_end', idx)
    if end < start:
        raise ValueError(f'row {idx}: date_end before date_start')
    if end > today:
        raise ValueError(f'row {idx}: date_end {end} is in the future')
    prec = _int(item, 'date_prec', idx)
    if not 1 <= prec <= 5:
        raise ValueError(f'row {idx}: date_prec {prec} not in 1-5')
    country_id = _int(item, 'country_id', idx)
    if country_id not in country_ids:
        raise ValueError(f'row {idx}: country_id {country_id} was not requested')
    violence = _int(item, 'type_of_violence', idx)
    if violence not in (1, 2, 3):
        raise ValueError(f'row {idx}: type_of_violence {violence} not in 1-3')
    best = _int(item, 'best', idx)
    if best < 0:
        raise ValueError(f'row {idx}: best is negative')
    country = item.get('country')
    if not isinstance(country, str) or not country.strip():
        raise ValueError(f'row {idx}: country is missing')
    region = item.get('region') or ''
    return GedRow(str(event_id).strip(), start, end, prec, country.strip(),
                  country_id, str(region).strip(), violence, best)


def parse_page(payload, today, country_ids=MIDEAST_COUNTRY_IDS, offset=0):
    if not isinstance(payload, dict) or not isinstance(payload.get('Result'), list):
        raise ValueError('unexpected UCDP response shape (no Result list)')
    for key in ('TotalCount', 'TotalPages'):
        if not isinstance(payload.get(key), int) or payload[key] < 0:
            raise ValueError(f'unexpected UCDP response shape ({key})')
    return [parse_row(item, offset + i, today, set(country_ids))
            for i, item in enumerate(payload['Result'])]


def _checked_next(url):
    """Follow NextPageUrl only to the UCDP API host over https."""
    if not url:
        return None
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != API_HOST:
        raise ValueError('NextPageUrl points outside the UCDP API')
    return url


def fetch_ged(version, token, today, get=http_get, pagesize=DEFAULT_PAGESIZE,
              country_ids=MIDEAST_COUNTRY_IDS):
    url, rows, total, pages = first_url(version, pagesize, country_ids), [], None, 0
    while url:
        pages += 1
        if pages > MAX_PAGES:
            raise ValueError(f'more than {MAX_PAGES} pages; stopping')
        try:
            payload = json.loads(get(url, token).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError('UCDP response is not JSON') from None
        page_rows = parse_page(payload, today, country_ids, len(rows))
        if total is None:
            total = payload['TotalCount']
        elif payload['TotalCount'] != total:
            raise ValueError('TotalCount changed between pages')
        if not page_rows and payload.get('NextPageUrl'):
            raise ValueError('empty page before the last page')
        rows.extend(page_rows)
        url = _checked_next(payload.get('NextPageUrl'))
    if total is None or len(rows) != total:
        raise ValueError(f'got {len(rows)} rows, TotalCount says {total}')
    return rows


def read_existing(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def validate(rows, existing=(), min_rows=MIN_ROWS):
    """Reject a short or truncated download before it can replace a good file."""
    if len(rows) < min_rows:
        raise ValueError(f'only {len(rows)} rows; expected at least {min_rows}')
    ids = [r.id for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate GED ids')
    if existing and len(rows) < len(existing) * 0.99:
        raise ValueError(f'{len(rows)} rows would replace {len(existing)}')


def write_csv(rows, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for r in sorted(rows, key=lambda r: (r.date_start, r.country_id, r.id)):
            writer.writerow([r.id, r.date_start.isoformat(), r.date_end.isoformat(),
                             r.date_prec, r.country, r.country_id, r.region,
                             r.type_of_violence, r.best])
    tmp.replace(out)


def read_ged_csv(path):
    """Read data/ucdp/ged_mideast.csv back into GedRows."""
    with Path(path).open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValueError(f'{Path(path).name}: columns must be {",".join(CSV_COLUMNS)}')
        out = []
        for n, r in enumerate(reader, start=2):
            try:
                out.append(GedRow(r['id'], date.fromisoformat(r['date_start']),
                                  date.fromisoformat(r['date_end']), int(r['date_prec']),
                                  r['country'], int(r['country_id']), r['region'],
                                  int(r['type_of_violence']), int(r['best'])))
            except (TypeError, ValueError):
                raise ValueError(f'{Path(path).name} line {n}: bad value') from None
        return out


def main(argv=None, get=http_get, out=OUT, today=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--version', default=os.environ.get('UCDP_VERSION', DEFAULT_VERSION))
    parser.add_argument('--pagesize', type=int, default=DEFAULT_PAGESIZE)
    parser.add_argument('--min-rows', type=int, default=MIN_ROWS)
    args = parser.parse_args(argv)
    token = os.environ.get('UCDP_TOKEN', '').strip()
    if not token:
        print('UCDP_TOKEN is not set; the UCDP API says a token is required. Trying anyway.',
              file=sys.stderr)
    today = today or date.today()
    try:
        rows = fetch_ged(args.version, token, today, get, args.pagesize)
        validate(rows, read_existing(out), args.min_rows)
    except (RuntimeError, ValueError, KeyError) as err:
        message = str(err)
        if token:
            message = message.replace(token, '***')
        print(f'ucdp: not written ({message})', file=sys.stderr)
        return 1
    write_csv(rows, out)
    days = sorted(r.date_start for r in rows)
    print(f'ucdp: GED {args.version}, {len(rows)} events, {days[0]} to {days[-1]}, '
          f'{len({r.country_id for r in rows})} countries')
    return 0


if __name__ == '__main__':
    sys.exit(main())
