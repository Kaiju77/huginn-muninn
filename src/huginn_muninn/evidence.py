"""Recorded evidence for the night desk.

Live retrieval stays off. An observation is ingested from a local fixture
or from a caller. It is not copied into the ledger.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
from typing import NamedTuple


MAX_AGE_DAYS = 7

_REASON_ORDER = (
    'invalid_observation',
    'invalid_id',
    'invalid_source',
    'unknown_source',
    'excluded',
    'invalid_subject',
    'invalid_unit',
    'blank_provenance',
    'json_number',
    'non_finite',
    'invalid_value',
    'invalid_date',
    'invalid_quality',
    'conflict',
)


class Observation(NamedTuple):
    observation_id: str
    source_id: str
    subject: str
    unit: str
    value: object
    observation_time: date
    retrieval_time: date
    provenance: str
    quality: tuple


class IngestResult(NamedTuple):
    stored: bool
    duplicate: bool
    conflict: bool
    reasons: tuple


class Conflict(NamedTuple):
    observation_id: str
    values: tuple


class Assessment(NamedTuple):
    limitations: tuple


def _ordered(reasons):
    found = set(reasons)
    return tuple(reason for reason in _REASON_ORDER if reason in found)


def _blank(value):
    return not isinstance(value, str) or value.strip() == ''


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_value(value):
    """Return (amount, reasons). None means the fixture marked the value missing."""
    if value is None:
        return None, ()
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return None, ('json_number',)
    if not isinstance(value, str):
        return None, ('json_number',)
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None, ('invalid_value',)
    if not amount.is_finite():
        return None, ('non_finite',)
    return amount, ()


def _as_of(value):
    if isinstance(value, date):
        return value
    parsed = _parse_date(value)
    if parsed is None:
        raise ValueError('invalid date')
    return parsed


def _age_window(max_age_days):
    if isinstance(max_age_days, bool) or not isinstance(max_age_days, int):
        raise ValueError('invalid age')
    if max_age_days < 0:
        raise ValueError('invalid age')
    return max_age_days


def freshness_flags(observation, as_of, max_age_days):
    """Caller-supplied dates only. This does not read the wall clock."""
    day = _as_of(as_of)
    window = _age_window(max_age_days)
    flags = []
    if observation.value is None:
        flags.append('missing_value')
    if observation.observation_time > day:
        flags.append('future_observation')
    if observation.retrieval_time > day:
        flags.append('future_retrieval')
    age = (day - observation.observation_time).days
    if age > window:
        flags.append('stale')
    if not flags:
        flags.append('fresh')
    return tuple(flags)


def load_registry(path):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    rows = document.get('sources')
    if not isinstance(rows, list) or not rows:
        raise ValueError('sources are required')
    sources = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('source must be an object')
        if row.get('live_fetch') is not False:
            raise ValueError('live_fetch must be false')
        source_id = row.get('source_id')
        if _blank(source_id) or source_id in seen:
            raise ValueError('source_id is required')
        seen.add(source_id)
        sources.append(dict(row))
    return tuple(sources)


def _cache_row(row):
    if not isinstance(row, dict):
        return {'invalid_observation': True}
    copied = {}
    for key, value in row.items():
        if isinstance(value, tuple):
            copied[key] = list(value)
        elif isinstance(value, Decimal):
            copied[key] = format(value, 'f')
        else:
            copied[key] = value
    return copied


class EvidenceStore:
    """In-memory observations. An optional cache replays through ingest."""

    def __init__(self, sources, cache_path=None, live_retrieval=False):
        if live_retrieval is not False:
            raise ValueError('live_retrieval must be false')
        self.live_retrieval = False
        self._sources = []
        seen = set()
        for source in sources:
            if not isinstance(source, dict) or source.get('live_fetch') is not False:
                raise ValueError('live_fetch must be false')
            source_id = source.get('source_id')
            if _blank(source_id) or source_id in seen:
                raise ValueError('source_id is required')
            seen.add(source_id)
            self._sources.append(dict(source))
        self.cache_path = None if cache_path is None else Path(cache_path)
        self._observations = []
        self._index = {}
        self._conflicts = {}
        self._submissions = []
        self._suspend_cache = False

    def sources(self):
        return tuple(self._sources)

    def observations(self):
        return tuple(self._observations)

    def conflicts(self):
        return tuple(
            Conflict(observation_id, tuple(values))
            for observation_id, values in self._conflicts.items()
        )

    def _find_source(self, source_id):
        for source in self._sources:
            if source.get('source_id') == source_id:
                return source
        return None

    def ingest(self, row):
        result = self._accept(row)
        if self.cache_path is not None and not self._suspend_cache:
            self._submissions.append(_cache_row(row))
            self._write_cache()
        return result

    def _accept(self, row):
        if not isinstance(row, dict):
            return IngestResult(False, False, False, ('invalid_observation',))
        reasons = []
        observation_id = row.get('observation_id')
        if _blank(observation_id):
            reasons.append('invalid_id')
        source_id = row.get('source_id')
        if _blank(source_id):
            reasons.append('invalid_source')
        else:
            source = self._find_source(source_id)
            if source is None:
                reasons.append('unknown_source')
            elif source.get('status') == 'excluded' or source.get('category') == 'excluded':
                reasons.append('excluded')
        subject = row.get('subject')
        if _blank(subject):
            reasons.append('invalid_subject')
        unit = row.get('unit')
        if _blank(unit):
            reasons.append('invalid_unit')
        provenance = row.get('provenance')
        if _blank(provenance):
            reasons.append('blank_provenance')
        if 'value' not in row:
            amount = None
            reasons.append('invalid_value')
        else:
            amount, value_reasons = _parse_value(row.get('value'))
            reasons.extend(value_reasons)
        observation_time = _parse_date(row.get('observation_time'))
        retrieval_time = _parse_date(row.get('retrieval_time'))
        if observation_time is None or retrieval_time is None:
            reasons.append('invalid_date')
        quality = row.get('quality', ())
        if quality is None:
            quality = ()
        if isinstance(quality, tuple):
            quality = list(quality)
        if (
            not isinstance(quality, list)
            or any(_blank(flag) for flag in quality)
        ):
            reasons.append('invalid_quality')
            quality = ()
        if reasons:
            return IngestResult(False, False, False, _ordered(reasons))
        existing = self._index.get(observation_id)
        if existing is not None:
            if existing.value == amount:
                return IngestResult(False, True, False, ())
            values = self._conflicts.setdefault(observation_id, [existing.value])
            if amount not in values:
                values.append(amount)
            return IngestResult(False, False, True, ('conflict',))
        stored = Observation(
            observation_id,
            source_id,
            subject,
            unit,
            amount,
            observation_time,
            retrieval_time,
            provenance,
            tuple(quality),
        )
        self._observations.append(stored)
        self._index[observation_id] = stored
        return IngestResult(True, False, False, ())

    def _write_cache(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'submissions': self._submissions}
        text = json.dumps(payload, indent=2) + '\n'
        self.cache_path.write_text(text, encoding='utf-8')

    def load_cache(self):
        """Replay the submission log through ingest. A conflict stays a conflict."""
        if self.cache_path is None or not self.cache_path.is_file():
            return
        document = json.loads(self.cache_path.read_text(encoding='utf-8'))
        submissions = document.get('submissions')
        if not isinstance(submissions, list):
            raise ValueError('submissions are required')
        self._observations = []
        self._index = {}
        self._conflicts = {}
        self._submissions = []
        self._suspend_cache = True
        try:
            for row in submissions:
                self.ingest(row)
        finally:
            self._suspend_cache = False
        self._submissions = list(submissions)


def assess(store, as_of, max_age_days=MAX_AGE_DAYS):
    """Limitations only. There is no recommendation and no probability."""
    day = _as_of(as_of)
    window = _age_window(max_age_days)
    limitations = []
    observations = store.observations()
    synthetic = store.live_retrieval is False or any(
        'synthetic_fixture' in observation.quality for observation in observations
    )
    if synthetic:
        limitations.append('synthetic fixture')
    if any('stale' in freshness_flags(observation, day, window) for observation in observations):
        limitations.append('stale')
    if store.conflicts():
        limitations.append('conflict')
    if any(source.get('live_fetch') is False for source in store.sources()):
        limitations.append('source not connected')
    if any(
        source.get('status') == 'excluded' or source.get('source_id') == 'social-unverified'
        for source in store.sources()
    ):
        limitations.append('excluded social source')
    return Assessment(tuple(limitations))


def open_evidence(checkout, cache_path=None):
    root = Path(checkout)
    sources = load_registry(root / 'fixtures' / 'source_registry.json')
    document = json.loads(
        (root / 'fixtures' / 'evidence_observations.json').read_text(encoding='utf-8')
    )
    if document.get('live_retrieval') is not False:
        raise ValueError('live_retrieval must be false')
    rows = document.get('observations')
    if not isinstance(rows, list):
        raise ValueError('observations are required')
    store = EvidenceStore(sources, cache_path=cache_path, live_retrieval=False)
    for row in rows:
        result = store.ingest(row)
        if not result.stored:
            raise ValueError('fixture observation was not stored')
    return store
