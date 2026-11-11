#!/usr/bin/env python3
"""Fetch daily Brent spot prices (EIA series RBRTE) into data/prices/brent_daily.csv.

Needs the environment variable EIA_API_KEY. Runs in GitHub Actions; the key
is a repository secret and is never written to disk or printed.

Usage:
    python scripts/fetch_eia_brent.py [--out data/prices/brent_daily.csv]

Exit codes: 0 ok, 1 fetch or validation failed (the existing CSV is left
untouched), 2 no API key.
"""

import argparse
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
DEFAULT_OUT = ROOT / 'data' / 'prices' / 'brent_daily.csv'
ENDPOINT = 'https://api.eia.gov/v2/petroleum/pri/spt/data/'
SERIES = 'RBRTE'
PAGE = 5000
FIRST_DATE = date(1987, 5, 20)


def page_url(api_key, offset):
    params = [
        ('api_key', api_key),
        ('frequency', 'daily'),
        ('data[0]', 'value'),
        ('facets[series][]', SERIES),
        ('sort[0][column]', 'period'),
        ('sort[0][direction]', 'asc'),
        ('offset', str(offset)),
        ('length', str(PAGE)),
    ]
    return ENDPOINT + '?' + urllib.parse.urlencode(params)


def get_json(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt == retries - 1:
                # Never echo the URL: it contains the key.
                raise RuntimeError(f'EIA request failed: {type(err).__name__}') from None
            time.sleep(2 ** attempt * 5)
    raise AssertionError('unreachable')


def parse_rows(payload):
    """Return [(date, float)] from one EIA v2 response. Raises ValueError."""
    try:
        data = payload['response']['data']
    except (KeyError, TypeError):
        raise ValueError('unexpected EIA response shape') from None
    rows = []
    for item in data:
        if item.get('series') != SERIES:
            raise ValueError(f'unexpected series {item.get("series")!r}')
        value = item.get('value')
        if value is None or value == '':
            continue  # EIA marks a missing day with a null value; skip it.
        day = date.fromisoformat(item['period'])
        price = float(value)
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f'bad price {value!r} on {day}')
        rows.append((day, price))
    return rows


def validate(rows, today=None):
    today = today or date.today()
    if len(rows) < 1000:
        raise ValueError(f'only {len(rows)} rows; expected thousands')
    days = [d for d, _ in rows]
    if days != sorted(days) or len(set(days)) != len(days):
        raise ValueError('dates are not strictly increasing')
    if days[0] > FIRST_DATE.replace(year=FIRST_DATE.year + 1):
        raise ValueError(f'history starts late: {days[0]}')
    if days[-1] > today:
        raise ValueError(f'future date {days[-1]}')


def fetch_all(api_key, get=get_json):
    rows, offset = [], 0
    while True:
        payload = get(page_url(api_key, offset))
        batch = parse_rows(payload)
        rows.extend(batch)
        total = int(payload['response'].get('total', 0))
        offset += PAGE
        if offset >= total or not payload['response']['data']:
            break
    rows.sort()
    return rows


def write_csv(rows, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['date', 'usd_per_barrel'])
        for day, price in rows:
            writer.writerow([day.isoformat(), f'{price:g}'])
    tmp.replace(out)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    api_key = os.environ.get('EIA_API_KEY', '').strip()
    if not api_key:
        print('EIA_API_KEY is not set.', file=sys.stderr)
        return 2
    try:
        rows = fetch_all(api_key)
        validate(rows)
    except (RuntimeError, ValueError) as err:
        print(f'Not written: {err}', file=sys.stderr)
        return 1
    write_csv(rows, args.out)
    print(f'Wrote {len(rows)} rows, {rows[0][0]} to {rows[-1][0]}, to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
