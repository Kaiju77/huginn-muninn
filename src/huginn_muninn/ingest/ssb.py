"""Statistics Norway Statbank adapter.

live_fetch stays false. refresh_public does not call this module.
A bounded live query was not locked in this increment.
Table 03013 is discontinued through 2025M12 and is not called.
A current table id is still an open human decision.
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
