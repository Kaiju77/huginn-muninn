"""Norges Bank open-data exchange rates and interest rates.

The policy-rate key IR/K.POL.NOK returned HTTP 404 on 2026-10-11.
That key stays rejected. The verified policy-rate key is IR/B.KPRA.SD.R.
The NOWA rate key is SHORT_RATES/B.NOWA.ON.R. Volume, transaction, and
index rows are not stored.
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
    'That key stays rejected. The verified policy-rate key is IR/B.KPRA.SD.R.'
)
POLICY_RATE_SERIES = 'IR/B.KPRA.SD.R'
NOWA_SERIES = 'SHORT_RATES/B.NOWA.ON.R'

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


def policy_rate_url(start_period, end_period):
    return exchange_url(POLICY_RATE_SERIES, start_period, end_period)


def nowa_url(start_period, end_period):
    return exchange_url(NOWA_SERIES, start_period, end_period)


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


def _amount_ok(raw_value):
    try:
        amount = Decimal(raw_value)
    except InvalidOperation:
        return False
    return amount.is_finite()


def _blank_rate_row(record):
    period = record.get('TIME_PERIOD') or ''
    raw_value = record.get('OBS_VALUE')
    instrument = record.get('INSTRUMENT_TYPE') or ''
    tenor = record.get('TENOR') or ''
    measure = record.get('UNIT_MEASURE') or ''
    return (
        period == ''
        and (raw_value is None or raw_value == '')
        and instrument == ''
        and tenor == ''
        and measure == ''
    )


def _rate_reader(body, url, retrieval_time, origin):
    text = _decode(body)
    if text is None or not _date_ok(retrieval_time):
        return None, AdapterResult((), _parse_error(url, body, retrieval_time or '', origin, 'body'))
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    fieldnames = reader.fieldnames or ()
    required = {'TIME_PERIOD', 'OBS_VALUE', 'INSTRUMENT_TYPE', 'TENOR', 'UNIT_MEASURE'}
    if not required.issubset(set(fieldnames)):
        return None, AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'header'))
    return reader, None


def _percent_row(observation_id, subject, raw_value, period, retrieval_time, url, origin):
    return {
        'observation_id': observation_id,
        'source_id': 'norges-bank-open-data',
        'subject': subject,
        'unit': 'percent',
        'value': raw_value,
        'observation_time': period,
        'retrieval_time': retrieval_time,
        'provenance': 'Norges Bank open data. URL: ' + url,
        'quality': _quality(origin),
    }


def parse_policy_rate(body, url, retrieval_time, origin):
    """Parse the key policy rate. Another tenor rejects the whole body."""
    reader, failed = _rate_reader(body, url, retrieval_time, origin)
    if failed is not None:
        return failed
    rows = []
    for record in reader:
        if _blank_rate_row(record):
            continue
        period = record.get('TIME_PERIOD') or ''
        raw_value = record.get('OBS_VALUE')
        instrument = record.get('INSTRUMENT_TYPE') or ''
        tenor = record.get('TENOR') or ''
        measure = record.get('UNIT_MEASURE') or ''
        if instrument != 'KPRA' or tenor != 'SD' or measure != 'R':
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'tenor'))
        if raw_value is None or raw_value == '' or not _date_ok(period) or not _amount_ok(raw_value):
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'row'))
        rows.append(_percent_row(
            'nb-ir-KPRA-SD-' + period,
            'policy-rate',
            raw_value,
            period,
            retrieval_time,
            url,
            origin,
        ))
    if not rows:
        return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'empty'))
    return AdapterResult(tuple(rows), None)


def parse_nowa(body, url, retrieval_time, origin):
    """Parse the NOWA rate. Volume, transaction, and index rows are skipped."""
    reader, failed = _rate_reader(body, url, retrieval_time, origin)
    if failed is not None:
        return failed
    rows = []
    for record in reader:
        if _blank_rate_row(record):
            continue
        instrument = record.get('INSTRUMENT_TYPE') or ''
        tenor = record.get('TENOR') or ''
        measure = record.get('UNIT_MEASURE') or ''
        if instrument != 'NOWA' or tenor != 'ON' or measure != 'R':
            continue
        period = record.get('TIME_PERIOD') or ''
        raw_value = record.get('OBS_VALUE')
        if raw_value is None or raw_value == '' or not _date_ok(period) or not _amount_ok(raw_value):
            return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'row'))
        rows.append(_percent_row(
            'nb-short-NOWA-ON-R-' + period,
            'nowa',
            raw_value,
            period,
            retrieval_time,
            url,
            origin,
        ))
    if not rows:
        return AdapterResult((), _parse_error(url, body, retrieval_time, origin, 'empty'))
    return AdapterResult(tuple(rows), None)


async def _fetch_parsed(client, url, parser):
    fetched = await client.fetch_async(url)
    if not fetched.ok:
        return AdapterResult((), fetched)
    retrieval_time = fetched.retrieved_at[:10]
    return parser(fetched.body, url, retrieval_time, fetched.origin)


async def fetch_usd_nok(client, start_period, end_period):
    url = usd_nok_url(start_period, end_period)
    return await _fetch_parsed(client, url, parse_exr)


async def fetch_eur_nok(client, start_period, end_period):
    url = eur_nok_url(start_period, end_period)
    return await _fetch_parsed(client, url, parse_exr)


async def fetch_policy_rate(client, start_period, end_period):
    url = policy_rate_url(start_period, end_period)
    return await _fetch_parsed(client, url, parse_policy_rate)


async def fetch_nowa(client, start_period, end_period):
    url = nowa_url(start_period, end_period)
    return await _fetch_parsed(client, url, parse_nowa)
