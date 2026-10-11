"""ECB statistical data warehouse exchange rates.

Free reuse requires the source to be quoted and the figures to stay unmodified.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
import csv
import io

from src.huginn_muninn.ingest.client import FetchResult
from src.huginn_muninn.ingest.norges import AdapterResult


HOST = 'data-api.ecb.europa.eu'
SERIES = 'EXR/D.NOK.EUR.SP00.A'
USAGE_POLICY = (
    'https://www.ecb.europa.eu/stats/ecb_statistics/'
    'governance_and_quality_framework/html/usage_policy.en.html'
)
CITATION = 'Source: ECB statistics.'


def nok_eur_url(start_period, end_period):
    return (
        'https://data-api.ecb.europa.eu/service/data/EXR/D.NOK.EUR.SP00.A'
        '?format=csvdata&startPeriod='
        + start_period
        + '&endPeriod='
        + end_period
    )


def _quality(origin):
    if origin == 'live':
        return ['live_retrieval']
    return ['recorded_fixture']


def _date_ok(value):
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _parse_error(url, body, retrieval_time, origin, detail):
    raw = body if isinstance(body, bytes) else b''
    return FetchResult(
        False, 'parse_error', None, url, raw, retrieval_time or '', 0, origin or '', detail,
    )


def parse_nok_eur(body, url, retrieval_time, origin):
    """Parse csvdata. OBS_VALUE text is passed to Decimal unchanged."""
    if isinstance(body, bytes):
        try:
            text = body.decode('utf-8')
        except UnicodeDecodeError:
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'body'))
    elif isinstance(body, str):
        text = body
    else:
        return AdapterResult((), _parse_error(url, b'', retrieval_time, origin, 'body'))
    if not _date_ok(retrieval_time):
        return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'retrieval'))
    reader = csv.DictReader(io.StringIO(text), delimiter=',')
    fieldnames = reader.fieldnames or ()
    if 'TIME_PERIOD' not in fieldnames or 'OBS_VALUE' not in fieldnames:
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
        rows.append({
            'observation_id': 'ecb-exr-NOK-EUR-' + period,
            'source_id': 'ecb-sdw',
            'subject': 'EUR/NOK',
            'unit': 'NOK per 1 EUR',
            'value': raw_value,
            'observation_time': period,
            'retrieval_time': retrieval_time,
            'provenance': CITATION + ' URL: ' + url,
            'quality': _quality(origin),
        })
    if not rows:
        return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'empty'))
    return AdapterResult(tuple(rows), None)


async def fetch_nok_eur(client, start_period, end_period):
    url = nok_eur_url(start_period, end_period)
    fetched = await client.fetch_async(url)
    if not fetched.ok:
        return AdapterResult((), fetched)
    return parse_nok_eur(fetched.body, url, fetched.retrieved_at[:10], fetched.origin)
