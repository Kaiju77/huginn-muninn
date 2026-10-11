"""File cache for raw responses and one explicit refresh.

Reading this module does not open a socket.
"""

from hashlib import sha256
from pathlib import Path
import json
from typing import NamedTuple


class CacheView(NamedTuple):
    retrieved_at: object
    observations: tuple
    errors: tuple


def write_response(cache_dir, result):
    """Store the raw body, URL, status, and retrieval timestamp."""
    root = Path(cache_dir)
    bodies = root / 'bodies'
    entries = root / 'entries'
    bodies.mkdir(parents=True, exist_ok=True)
    entries.mkdir(parents=True, exist_ok=True)
    key = sha256(result.url.encode('utf-8')).hexdigest()
    body_name = key + '.body'
    (bodies / body_name).write_bytes(result.body or b'')
    payload = {
        'url': result.url,
        'status': result.status,
        'retrieved_at': result.retrieved_at,
        'reason': result.reason,
        'body_file': 'bodies/' + body_name,
    }
    text = json.dumps(payload, indent=2) + '\n'
    (entries / (key + '.json')).write_text(text, encoding='utf-8')


def write_refresh(cache_dir, retrieved_at, observations, errors):
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        'retrieved_at': retrieved_at,
        'observations': list(observations),
        'errors': [_error_dict(item) for item in errors],
    }
    text = json.dumps(payload, indent=2) + '\n'
    (root / 'refresh.json').write_text(text, encoding='utf-8')


def _error_dict(item):
    if isinstance(item, dict):
        return {
            'reason': item.get('reason') or '',
            'url': item.get('url') or '',
            'status': item.get('status'),
            'detail': item.get('detail') or '',
        }
    return {
        'reason': item.reason,
        'url': item.url,
        'status': item.status,
        'detail': item.detail,
    }


def _newest_entry_time(root):
    entries = root / 'entries'
    if not entries.is_dir():
        return None
    newest = None
    for path in entries.glob('*.json'):
        try:
            document = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = document.get('retrieved_at')
        if isinstance(stamp, str) and stamp.strip() != '':
            if newest is None or stamp > newest:
                newest = stamp
    return newest


def read_desk_cache(cache_dir):
    """Return stored refresh facts. This does not fetch."""
    root = Path(cache_dir)
    if not root.exists():
        return CacheView(None, (), ())
    retrieved = None
    observations = ()
    errors = []
    refresh = root / 'refresh.json'
    if refresh.is_file():
        try:
            document = json.loads(refresh.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return CacheView(
                None,
                (),
                ({'reason': 'parse_error', 'url': '', 'status': None, 'detail': 'refresh.json'},),
            )
        if not isinstance(document, dict):
            return CacheView(
                None,
                (),
                ({'reason': 'parse_error', 'url': '', 'status': None, 'detail': 'refresh.json'},),
            )
        stamp = document.get('retrieved_at')
        if isinstance(stamp, str) and stamp.strip() != '':
            retrieved = stamp
        raw_rows = document.get('observations')
        if isinstance(raw_rows, list):
            observations = tuple(row for row in raw_rows if isinstance(row, dict))
        raw_errors = document.get('errors')
        if isinstance(raw_errors, list):
            errors.extend(row for row in raw_errors if isinstance(row, dict))
    newest = _newest_entry_time(root)
    if retrieved is None:
        retrieved = newest
    elif newest is not None and newest > retrieved:
        retrieved = newest
    return CacheView(retrieved, observations, tuple(errors))
