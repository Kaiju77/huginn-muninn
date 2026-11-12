#!/usr/bin/env python3
"""Move a pending candidate into the event catalog.

    python scripts/approve_event.py c-20261111-iran [--title "..."] [--episode ...]

Runs from the approve-event workflow (one input field in GitHub). The new row
is validated with the normal catalog loader before anything is written.
"""

import argparse
import csv
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.suggest_events import CANDIDATES, read_candidates, write_candidates  # noqa: E402
from src.huginn_muninn.catalog import COLUMNS, load_catalog  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def approve(candidate_id, title=None, episode=None, events=EVENTS, candidates=CANDIDATES,
            day=None):
    rows = read_candidates(candidates)
    match = [r for r in rows if r['candidate_id'] == candidate_id]
    if not match:
        raise ValueError(f'no candidate {candidate_id}')
    cand = match[0]
    day = day or cand['date_public']
    event_id = f'me-{day[:4]}-{cand["region"]}-{day[5:7]}{day[8:10]}'
    with events.open(encoding='utf-8-sig', newline='') as handle:
        existing = list(csv.DictReader(handle))
    already = [r for r in existing if r['event_id'] == event_id]
    if already and candidate_id not in already[0].get('notes', ''):
        raise ValueError(f'{event_id} already exists in the catalog and was not added from '
                         f'{candidate_id}; add it by hand with a different event_id')
    if already and cand['status'] == 'pending':
        # An earlier run added the event but stopped before marking the
        # candidate: finish that run instead of failing.
        cand['status'] = 'approved'
        _atomic_write_candidates(rows, candidates)
        return already[0]
    if cand['status'] != 'pending':
        raise ValueError(f'{candidate_id} is already {cand["status"]}')
    new_row = {
        'event_id': event_id, 'date_public': day,
        'title': (title or cand['title']).strip(), 'category': 'mideast-conflict',
        'region': cand['region'],
        'episode': episode or cand['episode_hint'] or f'{day[:4]}-{cand["region"]}-{day[5:7]}{day[8:10]}',
        'source_url': cand['source_url'], 'source_checked': 'no',
        'notes': f'Approved from headline candidate {candidate_id} ({cand["n_sites"]} sites).',
    }
    existing.append(new_row)
    existing.sort(key=lambda r: (r['date_public'], r['event_id']))
    # Write next to the target and swap in with os.replace (atomic on one file
    # system), so an interruption leaves either the old or the new catalog.
    trial = events.with_name(events.name + '.tmp')
    try:
        with trial.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(existing)
        load_catalog(trial, category='mideast-conflict')  # raises on any problem
        os.replace(trial, events)
    finally:
        if trial.exists():
            trial.unlink()
    cand['status'] = 'approved'
    _atomic_write_candidates(rows, candidates)
    return new_row


def _atomic_write_candidates(rows, path):
    tmp = path.with_name(path.name + '.tmp')
    write_candidates(rows, tmp)
    os.replace(tmp, path)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('candidate_id')
    p.add_argument('--title')
    p.add_argument('--episode')
    p.add_argument('--date', help='YYYY-MM-DD, to correct the public date')
    a = p.parse_args(argv)
    try:
        if a.date:
            date.fromisoformat(a.date)
        row = approve(a.candidate_id.strip(), a.title, a.episode, day=a.date)
    except ValueError as err:
        print(f'Not approved: {err}', file=sys.stderr)
        return 1
    print(f'Added {row["event_id"]} ({row["date_public"]}, episode {row["episode"]}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
