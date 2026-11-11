#!/usr/bin/env python3
"""Add today's candidate events to data/events/candidates.csv.

    python scripts/suggest_events.py [--today YYYY-MM-DD]

Reads data/news/latest.json; only uses it if it was fetched on --today.
Existing candidate ids are not duplicated.
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.candidates import COLUMNS, suggest  # noqa: E402
from src.huginn_muninn.catalog import load_catalog  # noqa: E402

NEWS = ROOT / 'data' / 'news' / 'latest.json'
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
CANDIDATES = ROOT / 'data' / 'events' / 'candidates.csv'


def read_candidates(path=CANDIDATES):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_candidates(rows, path=CANDIDATES):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def run(today, news_path=NEWS, events_path=EVENTS, out=CANDIDATES):
    try:
        news = json.loads(news_path.read_text(encoding='utf-8'))
        fetched = datetime.fromisoformat(news['fetched_at']).astimezone(timezone.utc).date()
    except (OSError, ValueError, KeyError):
        return []
    if fetched != today:
        return []
    found = suggest(news['articles'], today, load_catalog(events_path))
    rows = read_candidates(out)
    known = {r['candidate_id'] for r in rows}
    new = [c for c in found if c.candidate_id not in known]
    for c in new:
        rows.append({'candidate_id': c.candidate_id, 'date_public': c.date_public.isoformat(),
                     'title': c.title, 'region': c.region, 'episode_hint': c.episode_hint,
                     'source_url': c.source_url, 'n_sites': c.n_sites, 'status': c.status})
    if new or not out.exists():
        write_candidates(rows, out)
    return new


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--today', type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    a = p.parse_args(argv)
    new = run(a.today)
    print(f'{len(new)} new candidate(s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
