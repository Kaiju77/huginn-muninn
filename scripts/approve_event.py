#!/usr/bin/env python3
"""Move a pending candidate into the event catalog.

    python scripts/approve_event.py c-20261111-iran [--title "..."] [--episode ...]

Runs from the approve-event workflow (one input field in GitHub). The new row
is validated with the normal catalog loader before anything is written.
"""

import argparse
import csv
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.suggest_events import CANDIDATES, read_candidates, write_candidates  # noqa: E402
from src.huginn_muninn.catalog import COLUMNS, load_catalog  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def approve(candidate_id, title=None, episode=None, events=EVENTS, candidates=CANDIDATES):
    rows = read_candidates(candidates)
    match = [r for r in rows if r['candidate_id'] == candidate_id]
    if not match:
        raise ValueError(f'no candidate {candidate_id}')
    cand = match[0]
    if cand['status'] != 'pending':
        raise ValueError(f'{candidate_id} is already {cand["status"]}')
    day = cand['date_public']
    event_id = f'me-{day[:4]}-{cand["region"]}-{day[5:7]}{day[8:10]}'
    new_row = {
        'event_id': event_id, 'date_public': day,
        'title': (title or cand['title']).strip(), 'category': 'mideast-conflict',
        'region': cand['region'],
        'episode': episode or cand['episode_hint'] or f'{day[:4]}-{cand["region"]}-{day[5:7]}{day[8:10]}',
        'source_url': cand['source_url'], 'source_checked': 'no',
        'notes': f'Approved from headline candidate {candidate_id} ({cand["n_sites"]} sites).',
    }
    with events.open(encoding='utf-8-sig', newline='') as handle:
        existing = list(csv.DictReader(handle))
    existing.append(new_row)
    existing.sort(key=lambda r: (r['date_public'], r['event_id']))
    with tempfile.TemporaryDirectory() as tmp:
        trial = Path(tmp) / events.name
        with trial.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(existing)
        load_catalog(trial, category='mideast-conflict')  # raises on any problem
        shutil.copyfile(trial, events)
    cand['status'] = 'approved'
    write_candidates(rows, candidates)
    return new_row


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('candidate_id')
    p.add_argument('--title')
    p.add_argument('--episode')
    a = p.parse_args(argv)
    try:
        row = approve(a.candidate_id.strip(), a.title, a.episode)
    except ValueError as err:
        print(f'Not approved: {err}', file=sys.stderr)
        return 1
    print(f'Added {row["event_id"]} ({row["date_public"]}, episode {row["episode"]}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
