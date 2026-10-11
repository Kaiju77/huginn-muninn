"""Norges Bank open-data exchange rates.

The policy-rate key IR/K.POL.NOK returned HTTP 404 on 2026-10-11.
This adapter does not invent a replacement key and does not request it.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
import csv
import io
from typing import NamedTuple

from src.huginn_muninn.ingest.client import FetchResult


POLICY_RATE_KEY = 'IR/K.POL.NOK'
POLICY_RATE_HTTP_STATUS = 404
POLICY_RATE_NOTE = (
    'IR/K.POL.NOK returned HTTP 404 on 2026-10-11. '
    'No replacement policy-rate key is invented.'
)

USD_NOK_SERIES = 'EXR/B.USD.NOK.SP'
EUR_NOK_SERIES = 'EXR/B.EUR.NOK.SP'
HOST = 'data.norges-bank.no'


class AdapterResult(NamedTuple):
    observations: tuple
    error: object


def exchange_url(series_path, start_period, end_period):
    return (
        'https://data.norges-bank.no/api/data/'
        + series_path
        + '?format=csv&startPeriod='
        + start_period
        + '&endPeriod='
        + end_period
    )


def usd_nok_url(start_period, end_period):
    return exchange_url(USD_NOK_SERIES, start_period, end_period)


def eur_nok_url(start_period, end_period):
    return exchange_url(EUR_NOK_SERIES, start_period, end_period)


def _quality(origin):
    if origin == 'live':
        return ['live_retrieval']
    return ['recorded_fixture']


def _decode(body):
    if isinstance(body, str):
        return body
    if not isinstance(body, bytes):
        return None
    try:
        return body.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _parse_error(url, body, retrieval_time, origin, detail):
    raw = body if isinstance(body, bytes) else b''
    return FetchResult(
        False, 'parse_error', None, url, raw, retrieval_time, 0, origin or '', detail,
    )


def _date_ok(value):
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def parse_exr(body, url, retrieval_time, origin):
    """Parse a semicolon CSV body. The COLLECTION column is not a source name."""
    text = _decode(body)
    if text is None or not _date_ok(retrieval_time):
        return AdapterResult((), _parse_error(url, body, retrieval_time or '', origin, 'body'))
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    fieldnames = reader.fieldnames or ()
    required = {'TIME_PERIOD', 'OBS_VALUE', 'BASE_CUR', 'QUOTE_CUR'}
    if not required.issubset(set(fieldnames)):
        return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'header'))
    rows = []
    for record in reader:
        period = record.get('TIME_PERIOD') or ''
        raw_value = record.get('OBS_VALUE')
        if period == '' and (raw_value is None or raw_value == ''):
            continue
        if raw_value is None or raw_value == '' or not _date_ok(period):
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'row'))
        try:
            amount = Decimal(raw_value)
        except InvalidOperation:
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'value'))
        if not amount.is_finite():
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'value'))
        base = record.get('BASE_CUR') or ''
        quote = record.get('QUOTE_CUR') or ''
        if base.strip() == '' or quote.strip() == '':
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'pair'))
        rows.append({
            'observation_id': 'nb-exr-' + base + '-' + quote + '-' + period,
            'source_id': 'norges-bank-open-data',
            'subject': base + '/' + quote,
            'unit': quote + ' per 1 ' + base,
            'value': raw_value,
            'observation_time': period,
            'retrieval_time': retrieval_time,
            'provenance': 'Norges Bank open data. URL: ' + url,
            'quality': _quality(origin),
        })
    if not rows:
        return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'empty'))
    return AdapterResult(tuple(rows), None)


async def fetch_usd_nok(client, start_period, end_period):
    url = usd_nok_url(start_period, end_period)
    fetched = await client.fetch_async(url)
    if not fetched.ok:
        return AdapterResult((), fetched)
    retrieval_time = fetched.retrieved_at[:10]
    return parse_exr(fetched.body, url, retrieval_time, fetched.origin)
