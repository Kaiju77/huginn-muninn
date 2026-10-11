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
    revisions: tuple


MAX_STORED_OBSERVATIONS = 500

_IDENTITY = (
    'source_id',
    'subject',
    'unit',
    'value',
    'observation_time',
    'retrieval_time',
    'provenance',
    'quality',
)


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


def _copy_row(row):
    copied = dict(row)
    quality = copied.get('quality')
    if isinstance(quality, (list, tuple)):
        copied['quality'] = list(quality)
    return copied


def _identity(row, key):
    value = row.get(key)
    if key == 'quality':
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return ()
    return value


def _same_stored_row(left, right):
    if left.get('observation_id') != right.get('observation_id'):
        return False
    return all(_identity(left, key) == _identity(right, key) for key in _IDENTITY)


def _same_revision(left, right):
    return (
        left.get('observation_id') == right.get('observation_id')
        and list(left.get('values') or []) == list(right.get('values') or [])
        and list(left.get('retrieval_times') or []) == list(right.get('retrieval_times') or [])
    )


def _load_prior(path):
    if not path.is_file():
        return [], []
    try:
        document = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(document, dict):
        return [], []
    observations = document.get('observations')
    revisions = document.get('revisions')
    if not isinstance(observations, list):
        observations = []
    if not isinstance(revisions, list):
        revisions = []
    return (
        [_copy_row(row) for row in observations if isinstance(row, dict)],
        [dict(row) for row in revisions if isinstance(row, dict)],
    )


def _protected_dates(observations):
    found = set()
    for row in observations:
        if isinstance(row, dict):
            found.add(row.get('observation_time') or '')
    return found


def _trim_observations(stored, protected_dates):
    if len(stored) <= MAX_STORED_OBSERVATIONS:
        return stored
    ranked = []
    for index, row in enumerate(stored):
        day = row.get('observation_time') or ''
        if day in protected_dates:
            continue
        ranked.append((day, index))
    ranked.sort()
    overflow = len(stored) - MAX_STORED_OBSERVATIONS
    remove = {index for _day, index in ranked[:overflow]}
    return [row for index, row in enumerate(stored) if index not in remove]


def _merge_observations(prior, incoming, prior_revisions):
    stored = list(prior)
    revisions = list(prior_revisions)
    for row in incoming:
        if not isinstance(row, dict):
            continue
        new = _copy_row(row)
        observation_id = new.get('observation_id')
        matches = [
            kept for kept in stored if kept.get('observation_id') == observation_id
        ]
        if any(_same_stored_row(kept, new) for kept in matches):
            continue
        if matches:
            previous = matches[-1]
            revision = {
                'observation_id': observation_id,
                'values': [previous.get('value'), new.get('value')],
                'retrieval_times': [
                    previous.get('retrieval_time'),
                    new.get('retrieval_time'),
                ],
            }
            if not any(_same_revision(item, revision) for item in revisions):
                revisions.append(revision)
        stored.append(new)
    stored = _trim_observations(stored, _protected_dates(incoming))
    return stored, revisions


def write_refresh(cache_dir, retrieved_at, observations, errors):
    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'refresh.json'
    prior_observations, prior_revisions = _load_prior(path)
    stored, revisions = _merge_observations(
        prior_observations,
        observations,
        prior_revisions,
    )
    payload = {
        'retrieved_at': retrieved_at,
        'observations': stored,
        'revisions': revisions,
        'errors': [_error_dict(item) for item in errors],
    }
    text = json.dumps(payload, indent=2) + '\n'
    path.write_text(text, encoding='utf-8')


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
        return CacheView(None, (), (), ())
    retrieved = None
    observations = ()
    errors = []
    revisions = []
    refresh = root / 'refresh.json'
    if refresh.is_file():
        try:
            document = json.loads(refresh.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return CacheView(
                None,
                (),
                ({'reason': 'parse_error', 'url': '', 'status': None, 'detail': 'refresh.json'},),
                (),
            )
        if not isinstance(document, dict):
            return CacheView(
                None,
                (),
                ({'reason': 'parse_error', 'url': '', 'status': None, 'detail': 'refresh.json'},),
                (),
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
        raw_revisions = document.get('revisions')
        if isinstance(raw_revisions, list):
            revisions.extend(row for row in raw_revisions if isinstance(row, dict))
    newest = _newest_entry_time(root)
    if retrieved is None:
        retrieved = newest
    elif newest is not None and newest > retrieved:
        retrieved = newest
    return CacheView(retrieved, observations, tuple(errors), tuple(revisions))
