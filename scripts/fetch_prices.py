#!/usr/bin/env python3
"""Fetch every daily price series in src/huginn_muninn/assets.py.

    python scripts/fetch_prices.py            # all assets
    python scripts/fetch_prices.py brent wti  # some

EIA series need the environment variable EIA_API_KEY (a GitHub secret).
Norges Bank needs no key. Each asset is fetched and validated on its own;
a failure leaves that asset's CSV untouched and makes the exit code 1.
A URL containing a key is never printed.
"""

import csv
import json
import math
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

from src.huginn_muninn.assets import ASSETS, BY_ID  # noqa: E402
from src.huginn_muninn.ingest.norges import parse_exr  # noqa: E402

EIA_BASE = 'https://api.eia.gov/v2/'
NB_BASE = 'https://data.norges-bank.no/api/data/'
PAGE = 5000
MIN_ROWS = 1000


def eia_url(asset, api_key, offset):
    params = [
        ('api_key', api_key), ('frequency', 'daily'), ('data[0]', 'value'),
        ('facets[series][]', asset.series),
        ('sort[0][column]', 'period'), ('sort[0][direction]', 'asc'),
        ('offset', str(offset)), ('length', str(PAGE)),
    ]
    return EIA_BASE + asset.route + '/data/?' + urllib.parse.urlencode(params)


def nb_url(asset, today):
    return (NB_BASE + asset.route + '?format=csv&startPeriod=1980-01-01&endPeriod='
            + today.isoformat())


def http_get(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt == retries - 1:
                raise RuntimeError(f'request failed: {type(err).__name__}') from None
            time.sleep(2 ** attempt * 5)
    raise AssertionError('unreachable')


def _check_price(asset, day, price):
    if not math.isfinite(price):
        raise ValueError(f'non-finite price on {day}')
    if price <= 0 and not asset.allow_nonpositive:
        raise ValueError(f'non-positive price {price} on {day}')


def parse_eia(asset, payload):
    try:
        data = payload['response']['data']
    except (KeyError, TypeError):
        raise ValueError('unexpected EIA response shape') from None
    rows = []
    for item in data:
        if item.get('series') != asset.series:
            raise ValueError(f'unexpected series {item.get("series")!r}')
        value = item.get('value')
        if value is None or value == '':
            continue
        day, price = date.fromisoformat(item['period']), float(value)
        _check_price(asset, day, price)
        rows.append((day, price))
    return rows


def fetch_eia(asset, api_key, get=http_get):
    rows, offset = [], 0
    while True:
        payload = json.loads(get(eia_url(asset, api_key, offset)).decode('utf-8'))
        rows.extend(parse_eia(asset, payload))
        total = int(payload['response'].get('total', 0))
        offset += PAGE
        if offset >= total or not payload['response']['data']:
            break
    return sorted(rows)


def fetch_norges(asset, today, get=http_get):
    url = nb_url(asset, today)
    result = parse_exr(get(url), url, today.isoformat(), 'live')
    if result.error is not None:
        raise ValueError('Norges Bank response did not parse')
    rows = []
    for obs in result.observations:
        day, price = date.fromisoformat(obs['observation_time']), float(obs['value'])
        _check_price(asset, day, price)
        rows.append((day, price))
    return sorted(rows)


def validate(rows, today):
    if len(rows) < MIN_ROWS:
        raise ValueError(f'only {len(rows)} rows; expected thousands')
    days = [d for d, _ in rows]
    if len(set(days)) != len(days):
        raise ValueError('duplicate dates')
    if days[-1] > today:
        raise ValueError(f'future date {days[-1]}')


def write_csv(rows, out, unit):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['date', unit])
        for day, price in rows:
            writer.writerow([day.isoformat(), f'{price:g}'])
    tmp.replace(out)


def fetch_one(asset, api_key, today, get=http_get):
    if asset.source == 'eia':
        if not api_key:
            raise RuntimeError('EIA_API_KEY is not set')
        rows = fetch_eia(asset, api_key, get)
    else:
        rows = fetch_norges(asset, today, get)
    validate(rows, today)
    return rows


def main(argv=None):
    ids = (argv if argv is not None else sys.argv[1:]) or [a.asset_id for a in ASSETS]
    unknown = [i for i in ids if i not in BY_ID]
    if unknown:
        print(f'Unknown asset(s): {", ".join(unknown)}', file=sys.stderr)
        return 2
    api_key = os.environ.get('EIA_API_KEY', '').strip()
    today, failed = date.today(), 0
    for asset_id in ids:
        asset = BY_ID[asset_id]
        try:
            rows = fetch_one(asset, api_key, today)
        except (RuntimeError, ValueError, KeyError) as err:
            print(f'{asset_id}: not written ({err})', file=sys.stderr)
            failed += 1
            continue
        write_csv(rows, asset.csv_path, asset.unit)
        print(f'{asset_id}: {len(rows)} rows, {rows[0][0]} to {rows[-1][0]}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
