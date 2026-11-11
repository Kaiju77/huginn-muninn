#!/usr/bin/env python3
"""Write the daily brief to reports/latest.md and reports/<date>.md.

    python scripts/daily_report.py [--today 2026-11-11]

Uses data/prices/*.csv, data/events/*.csv and data/news/latest.json.
Missing inputs are reported in the brief, not raised.
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn import daily  # noqa: E402
from src.huginn_muninn.assets import ASSETS, BY_ID  # noqa: E402
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import format_result  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
NEWS = ROOT / 'data' / 'news' / 'latest.json'
REPORTS = ROOT / 'reports'
DISCLAIMER = '_Historical base rates and headlines. Not a forecast or advice. You make the decisions._'


def pct(x, signed=True):
    if x is None:
        return 'n/a'
    return f'{x * 100:+.1f}%' if signed else f'{x * 100:.0f}%'


def unusual(rank):
    if rank is None:
        return 'n/a'
    if rank >= 0.95:
        return f'**larger than {rank * 100:.0f}% of days**'
    if rank >= 0.80:
        return f'larger than {rank * 100:.0f}% of days'
    return 'normal'


def build(today, prices_dir=None, events_path=EVENTS, news_path=NEWS, recent_days=90):
    lines = [f'# Daily market brief, {today.isoformat()}', '', DISCLAIMER, '']
    loaded = {}
    lines += ['## Moves', '',
              '| Asset | Latest close | Price | 1 day | 5 days | 1-day move vs history |',
              '|---|---|---|---|---|---|']
    for asset in ASSETS:
        path = (prices_dir / f'{asset.asset_id}.csv') if prices_dir else asset.csv_path
        if not path.exists():
            lines.append(f'| {asset.label} | no data yet | | | | |')
            continue
        # No look-ahead: a brief for ``today`` only sees closes up to today.
        closes = [c for c in load_closes(path) if c.on <= today]
        if len(closes) < 2:
            lines.append(f'| {asset.label} | no data on or before {today.isoformat()} | | | | |')
            continue
        loaded[asset.asset_id] = closes
        m = daily.move(asset.label, asset.unit, closes)
        lines.append(f'| {asset.label} | {m.on.isoformat()} | {m.close:g} {asset.unit} | '
                     f'{pct(m.change_1d)} | {pct(m.change_5d)} | {unusual(m.rank_1d)} |')
    lines += ['', 'EIA publishes a few days late, so the latest close can be several days old.', '']

    lines += [f'## Recent events (last {recent_days} days)', '']
    catalog = load_catalog(events_path)
    recent = daily.recent_events(catalog, today, recent_days)
    if not recent:
        last = max(catalog, key=lambda e: e.date_public)
        lines += [f'No catalog events in the last {recent_days} days. Latest: '
                  f'{last.title} ({last.date_public.isoformat()}). '
                  'The catalog is updated by hand for now.', '']
    for event in recent:
        comparable = [e for e in first_per_episode(catalog)
                      if e.episode != event.episode and e.date_public < event.date_public]
        lines += [f'### {event.title} ({event.date_public.isoformat()})', '',
                  f'Source: {event.source_url}', '']
        for asset_id in ('brent', 'wti', 'henry_hub', 'usd_nok'):
            if asset_id not in loaded:
                continue
            asset = BY_ID[asset_id]
            ctx = daily.event_context(event, comparable, loaded[asset_id])
            lines.append(f'**{asset.label}**: {ctx.days_since} trading days since the news, '
                         f'{pct(ctx.change_since)} since then. After comparable past events:')
            lines += [f'- {format_result(r, asset.label)}' for r in ctx.results]
            lines.append('')

    lines += ['## Headlines (GDELT, last 24 hours)', '']
    try:
        news = json.loads(news_path.read_text(encoding='utf-8'))
        fetched = datetime.fromisoformat(news['fetched_at'])
        age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        items = daily.headlines(news.get('articles', []))
        if age_h > 36:
            lines.append(f'News is {age_h:.0f} hours old; the last fetch may have failed.')
        if not items:
            lines.append('No matching headlines.')
        for title, domain, link, _seen in items:
            safe = title.replace('[', '(').replace(']', ')')
            lines.append(f'- [{safe}]({link}) ({domain})')
    except (OSError, ValueError, KeyError):
        lines.append('News unavailable.')
    lines += ['', 'Headlines from the same day are context. They do not prove why a price moved.', '']
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--today', type=date.fromisoformat, default=date.today())
    a = p.parse_args(argv)
    text = build(a.today)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / 'latest.md').write_text(text, encoding='utf-8')
    (REPORTS / f'{a.today.isoformat()}.md').write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
