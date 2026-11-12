#!/usr/bin/env python3
"""Add today's candidate events to data/events/candidates.csv.

    python scripts/suggest_events.py [--today YYYY-MM-DD]

Uses the AI screen (data/news/ai_screen.json) when it ran successfully for
--today; otherwise falls back to the keyword screen on data/news/latest.json.
Existing candidate ids are not duplicated.
"""

import argparse
import csv
import os
import re
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.candidates import COLUMNS, suggest  # noqa: E402
from src.huginn_muninn.catalog import load_catalog  # noqa: E402
from src.huginn_muninn.daily import in_window, parse_fetched  # noqa: E402

NEWS = ROOT / 'data' / 'news' / 'latest.json'
AI = ROOT / 'data' / 'news' / 'ai_screen.json'
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
CANDIDATES = ROOT / 'data' / 'events' / 'candidates.csv'


def _days_apart(row, cand):
    try:
        return abs((date.fromisoformat(row['date_public'])
                    - date.fromisoformat(cand['date_public'])).days)
    except (KeyError, TypeError, ValueError):
        return 99  # a hand-edited, unreadable date never matches (review round 10)


def _mostly_shared(a, b):
    if not a or not b:
        return False
    return len(a & b) >= max(1, (min(len(a), len(b)) + 1) // 2)


def _urls(row):
    return {u for u in (row.get('urls') or '').split('|') if u} | (
        {row['source_url']} if row.get('source_url') else set())


def read_candidates(path=CANDIDATES):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_candidates(rows, path=CANDIDATES):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.writing')
    with tmp.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, restval='')
        writer.writeheader()
        writer.writerows({k: r.get(k, '') for k in COLUMNS} for r in rows)
    os.replace(tmp, path)


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
        fetched = parse_fetched(news['fetched_at']).date()
    except (OSError, ValueError, KeyError):
        return []
    if fetched != today:
        return []
    fetched_at = parse_fetched(news['fetched_at'])
    articles = in_window(news['articles'], fetched_at)
    keyword = [{'candidate_id': c.candidate_id, 'date_public': c.date_public.isoformat(),
                'title': c.title, 'region': c.region, 'episode_hint': c.episode_hint,
                'source_url': c.source_url, 'n_sites': c.n_sites, 'status': 'pending',
                'method': 'keyword', 'event_type': '', 'urls': c.urls}
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
    new = []
    for c in found:
        base = c['candidate_id']
        slot = [r for r in rows if r['candidate_id'] == base
                or re.fullmatch(re.escape(base) + r'-\d+', r['candidate_id'])]
        mine = _urls(c)
        # Same story = at least one supporting article in common (or same title),
        # in this region within two days either side: robust to a new earliest
        # headline, an AI re-title (round 8) and a story spanning midnight or the
        # 12:00 cutoff (round 9).
        near = [r for r in rows if r['region'] == c['region'] and _days_apart(r, c) <= 2]
        # Same story: the same slot and the same title, or (within 2 days)
        # articles mostly shared. One shared round-up link is not enough, and a
        # repeated headline days later can be a new strike (review round 10).
        same = [r for r in near if _mostly_shared(_urls(r), mine)
                or (r in slot and r['title'] == c['title'])]
        if same:
            old = same[0]
            if (old['status'] == 'rejected' and old.get('method') == 'keyword'
                    and c.get('method') == 'ai'):
                # An AI candidate replaces a rejected keyword false alarm, keeping
                # that row's own id so ids stay unique (2026-11-12, review round 8).
                keep = old['candidate_id']
                old.update({k: c.get(k, '') for k in COLUMNS})
                old['candidate_id'] = keep
                new.append(dict(c, candidate_id=keep))
            elif old['status'] == 'pending':
                # Same story seen again: remember its new articles.
                old['urls'] = '|'.join(sorted(_urls(old) | mine))
            continue  # never revived, never duplicated
        if slot:
            # A different story for the same region and day keeps its own row.
            suffixes = [int(r['candidate_id'].rsplit('-', 1)[1]) for r in slot
                        if r['candidate_id'] != base]
            c = dict(c, candidate_id=f'{base}-{max(suffixes + [1]) + 1}')
        rows.append({k: c.get(k, '') for k in COLUMNS})
        new.append(c)
    changed = bool(new) or any(r.get('urls') for r in rows)
    if changed or not out.exists():
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
