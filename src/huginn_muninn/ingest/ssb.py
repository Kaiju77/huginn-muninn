"""Statistics Norway Statbank adapter.

Table 03013 is discontinued through 2025M12 and is not called.
Table 14700 replaces it. The only request is the 2026M07 total cell.
Other SSB tables are not requested.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
import json

from src.huginn_muninn.ingest.client import FetchResult
from src.huginn_muninn.ingest.norges import AdapterResult


HOST = 'data.ssb.no'
SOURCE_ID = 'ssb-statbank'


def _parse_error(detail):
    return FetchResult(False, 'parse_error', None, '', b'', '', 0, '', detail)


def parse_fixture(body, retrieval_time):
    """Parse one recorded statistical row. This does not fetch."""
    if isinstance(body, bytes):
        try:
            text = body.decode('utf-8')
        except UnicodeDecodeError:
            return AdapterResult((), _parse_error('body'))
    elif isinstance(body, str):
        text = body
    else:
        return AdapterResult((), _parse_error('body'))
    try:
        date.fromisoformat(retrieval_time)
        document = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return AdapterResult((), _parse_error('json'))
    if not isinstance(document, dict):
        return AdapterResult((), _parse_error('row'))
    subject = document.get('subject')
    unit = document.get('unit')
    raw_value = document.get('value')
    observed = document.get('time')
    if not all(isinstance(item, str) and item.strip() != '' for item in (
        subject, unit, raw_value, observed,
    )):
        return AdapterResult((), _parse_error('row'))
    try:
        date.fromisoformat(observed)
        amount = Decimal(raw_value)
    except (ValueError, InvalidOperation):
        return AdapterResult((), _parse_error('value'))
    if not amount.is_finite():
        return AdapterResult((), _parse_error('value'))
    row = {
        'observation_id': 'ssb-recorded-' + observed,
        'source_id': SOURCE_ID,
        'subject': subject,
        'unit': unit,
        'value': raw_value,
        'observation_time': observed,
        'retrieval_time': retrieval_time,
        'provenance': (
            'Statistics Norway Statbank recorded fixture. CC BY 4.0. '
            'Statistics, not security prices.'
        ),
        'quality': ['recorded_fixture'],
    }
    return AdapterResult((row,), None)


CPI_URL = 'https://data.ssb.no/api/pxwebapi/v2/tables/14700/data?lang=en&valueCodes[Tid]=2026M07&valueCodes[VareTjenesteGrp]=00&valueCodes[ContentsCode]=KpiIndMnd'
CPI_TIME = '2026M07'
CPI_PROVENANCE = (
    'Statistics Norway. CC BY 4.0. Table 14700. '
    'This is a price index, not a security price.'
)


def _cpi_error(url, body, retrieval_time, origin, detail):
    raw = body if isinstance(body, bytes) else b''
    return FetchResult(
        False, 'parse_error', None, url or '', raw, retrieval_time or '', 0, origin or '', detail,
    )


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


def _date_ok(value):
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _category_maps(document, name):
    dimension = document.get('dimension')
    if not isinstance(dimension, dict):
        return None
    node = dimension.get(name)
    if not isinstance(node, dict):
        return None
    category = node.get('category')
    if not isinstance(category, dict):
        return None
    index = category.get('index')
    label = category.get('label')
    if not isinstance(index, dict) or not isinstance(label, dict):
        return None
    return index, label


def _observation_day(time_code):
    """First day of 2026M07. Any other time code is rejected."""
    if time_code != CPI_TIME or len(time_code) != 7 or time_code[4] != 'M':
        return None
    year = int(time_code[:4])
    month = int(time_code[5:])
    return date(year, month, 1).isoformat()


def _table_id(document):
    extension = document.get('extension')
    if not isinstance(extension, dict):
        return None
    px = extension.get('px')
    if not isinstance(px, dict):
        return None
    table_id = px.get('tableid')
    if not isinstance(table_id, str):
        return None
    return table_id


def parse_cpi_total(body, url, retrieval_time, origin):
    """Parse the one table 14700 cell. A longer value list stores nothing."""
    text = _decode(body)
    if text is None or not _date_ok(retrieval_time):
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'body'))
    try:
        document = json.loads(text, parse_float=str)
    except json.JSONDecodeError:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'json'))
    if not isinstance(document, dict):
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'row'))
    values = document.get('value')
    if isinstance(values, list) and len(values) > 1:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'value'))
    if not isinstance(values, list) or len(values) != 1:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'value'))
    raw_value = values[0]
    if not isinstance(raw_value, str) or raw_value.strip() == '':
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'value'))
    try:
        amount = Decimal(raw_value)
    except InvalidOperation:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'value'))
    if not amount.is_finite():
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'value'))
    group = _category_maps(document, 'VareTjenesteGrp')
    contents = _category_maps(document, 'ContentsCode')
    period = _category_maps(document, 'Tid')
    if group is None or contents is None or period is None:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'cell'))
    group_index, group_label = group
    contents_index, _contents_label = contents
    period_index, _period_label = period
    if set(group_index) != {'00'} or group_label.get('00') != 'Total':
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'cell'))
    if set(contents_index) != {'KpiIndMnd'}:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'cell'))
    if set(period_index) != {CPI_TIME}:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'cell'))
    if _table_id(document) != '14700':
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'cell'))
    observed = _observation_day(CPI_TIME)
    if observed is None:
        return AdapterResult((), _cpi_error(url, body, retrieval_time, origin, 'cell'))
    row = {
        'observation_id': 'ssb-cpi-total-2026M07',
        'source_id': SOURCE_ID,
        'subject': 'cpi-total',
        'unit': 'index 2025=100',
        'value': raw_value,
        'observation_time': observed,
        'retrieval_time': retrieval_time,
        'provenance': CPI_PROVENANCE + ' URL: ' + url,
        'quality': _quality(origin),
    }
    return AdapterResult((row,), None)


async def fetch_cpi_total(client):
    """Request the one connected cell. The posted window does not change this URL."""
    fetched = await client.fetch_async(CPI_URL)
    if not fetched.ok:
        return AdapterResult((), fetched)
    return parse_cpi_total(fetched.body, CPI_URL, fetched.retrieved_at[:10], fetched.origin)
