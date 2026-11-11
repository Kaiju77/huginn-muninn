"""Load and validate a hand-curated event catalog (CSV).

Columns: event_id, date_public, title, category, region, episode,
source_url, source_checked, notes.

``episode`` groups events that belong to the same crisis (for example the
two 2019 Gulf of Oman tanker attacks). Events in one episode are not
independent, so ``first_per_episode`` keeps one event per episode before a
study counts them.
"""

import csv
from datetime import date
from pathlib import Path
from typing import NamedTuple

from src.huginn_muninn.study import Event

COLUMNS = (
    'event_id', 'date_public', 'title', 'category', 'region',
    'episode', 'source_url', 'source_checked', 'notes',
)


class CatalogEvent(NamedTuple):
    event_id: str
    date_public: date
    title: str
    category: str
    region: str
    episode: str
    source_url: str
    source_checked: bool
    notes: str

    def to_event(self) -> Event:
        return Event(self.event_id, self.date_public, self.title)


def load_catalog(path, category=None, today=None):
    """Return a list of CatalogEvent sorted by date. Raises ValueError with
    the row number on the first problem."""
    today = today or date.today()
    path = Path(path)
    # utf-8-sig accepts a byte-order mark from spreadsheet exports.
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        try:
            header = tuple(reader.fieldnames or ())
        except csv.Error as err:
            raise ValueError(f'{path.name}: bad CSV header ({err})') from None
        if header != COLUMNS:
            raise ValueError(f'{path.name}: columns must be {",".join(COLUMNS)}')
        events, seen = [], set()
        rows = iter(reader)
        while True:
            try:
                row = next(rows)
            except StopIteration:
                break
            except csv.Error as err:
                raise ValueError(f'{path.name} line {reader.line_num}: {err}') from None
            line = reader.line_num
            where = f'{path.name} line {line}'
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'{where}: expected {len(COLUMNS)} fields')
            for col in ('event_id', 'date_public', 'title', 'category', 'episode', 'source_url'):
                if not (row[col] or '').strip():
                    raise ValueError(f'{where}: {col} is empty')
            if row['event_id'] in seen:
                raise ValueError(f'{where}: duplicate event_id {row["event_id"]}')
            seen.add(row['event_id'])
            try:
                day = date.fromisoformat(row['date_public'])
            except ValueError:
                raise ValueError(f'{where}: date_public must be YYYY-MM-DD') from None
            if day > today:
                raise ValueError(f'{where}: date_public is in the future')
            if not row['source_url'].startswith('https://'):
                raise ValueError(f'{where}: source_url must start with https://')
            if row['source_checked'] not in ('yes', 'no'):
                raise ValueError(f'{where}: source_checked must be yes or no')
            if category is not None and row['category'] != category:
                raise ValueError(f'{where}: category {row["category"]} is not {category}')
            events.append(CatalogEvent(
                row['event_id'], day, row['title'], row['category'], row['region'],
                row['episode'], row['source_url'], row['source_checked'] == 'yes',
                row['notes'],
            ))
    return sorted(events, key=lambda e: (e.date_public, e.event_id))


def first_per_episode(events):
    """Keep the earliest event of each episode."""
    kept, seen = [], set()
    for event in sorted(events, key=lambda e: (e.date_public, e.event_id)):
        if event.episode not in seen:
            seen.add(event.episode)
            kept.append(event)
    return kept
