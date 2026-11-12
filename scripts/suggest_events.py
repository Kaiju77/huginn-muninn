#!/usr/bin/env python3
"""Add today's candidate events to data/events/candidates.csv.

    python scripts/suggest_events.py [--today YYYY-MM-DD]

Uses the AI screen (data/news/ai_screen.json) when it ran successfully for
--today; otherwise falls back to the keyword screen on data/news/latest.json.
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
from src.huginn_muninn.daily import in_window  # noqa: E402

NEWS = ROOT / 'data' / 'news' / 'latest.json'
AI = ROOT / 'data' / 'news' / 'ai_screen.json'
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
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, restval='')
        writer.writeheader()
        writer.writerows({k: r.get(k, '') for k in COLUMNS} for r in rows)


def ai_status(today, path=AI):
    """The AI screen result for ``today``, or None if it did not run ok today."""
    try:
        status = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if status.get('ok') and status.get('date') == today.isoformat():
        return status
    return None


def run(today, news_path=NEWS, events_path=EVENTS, out=CANDIDATES, ai_path=AI):
    try:
        news = json.loads(news_path.read_text(encoding='utf-8'))
        fetched = datetime.fromisoformat(news['fetched_at']).astimezone(timezone.utc).date()
    except (OSError, ValueError, KeyError):
        return []
    if fetched != today:
        return []
    fetched_at = datetime.fromisoformat(news['fetched_at'])
    articles = in_window(news['articles'], fetched_at)
    keyword = [{'candidate_id': c.candidate_id, 'date_public': c.date_public.isoformat(),
                'title': c.title, 'region': c.region, 'episode_hint': c.episode_hint,
                'source_url': c.source_url, 'n_sites': c.n_sites, 'status': 'pending',
                'method': 'keyword', 'event_type': ''}
               for c in suggest(articles, today, load_catalog(events_path))]
    ai = ai_status(today, ai_path)
    if ai is None:
        found = keyword
    else:
        found = [{**c, 'status': 'pending', 'method': 'ai'} for c in ai['candidates']]
        if ai.get('rejected'):
            # The model proposed something that failed validation; don't let that
            # hide what the keyword screen found in other regions.
            covered = {c['region'] for c in found}
            found += [c for c in keyword if c['region'] not in covered]
    rows = read_candidates(out)
    by_id = {r['candidate_id']: r for r in rows}
    new = []
    for c in found:
        old = by_id.get(c['candidate_id'])
        if old is None:
            rows.append({k: c.get(k, '') for k in COLUMNS})
            new.append(c)
        elif old['status'] == 'rejected' and old['title'] != c['title']:
            # A rejected suggestion must not hide a different one for the same
            # region and day (found 2026-11-12: a rejected keyword false alarm
            # blocked a later AI candidate).
            old.update({k: c.get(k, '') for k in COLUMNS})
            new.append(c)
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
