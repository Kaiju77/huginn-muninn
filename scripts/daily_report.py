#!/usr/bin/env python3
"""Write the daily brief to reports/latest.md and reports/<date>.md.

    python scripts/daily_report.py [--today 2026-11-11]

Uses data/prices/*.csv, data/events/*.csv and data/news/latest.json.
Missing inputs are reported in the brief, not raised.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn import daily  # noqa: E402
from src.huginn_muninn.mdsafe import md, url  # noqa: E402
from src.huginn_muninn.assets import ASSETS, BY_ID  # noqa: E402
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import format_result  # noqa: E402
from scripts.suggest_events import AI, CANDIDATES, ai_status, read_candidates  # noqa: E402

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


def news_lines(today, news_path):
    """Headlines only if they were fetched on ``today`` (UTC). Anything else is
    either a failed refresh or a past brief, and is said plainly."""
    try:
        news = json.loads(news_path.read_text(encoding='utf-8'))
        fetched = daily.parse_fetched(news['fetched_at'])
        articles = news['articles']
    except (OSError, ValueError, KeyError, TypeError):
        return ['News unavailable.']
    fetched_day = fetched.astimezone(timezone.utc).date()
    if fetched_day != today:
        return [f'No headlines fetched on {today.isoformat()} (the latest fetch is from '
                f'{fetched_day.isoformat()}; today\'s fetch failed or has not run).']
    items = daily.headlines(daily.in_window(articles, fetched))
    if not items:
        return ['News unavailable (the fetch returned no usable headlines).']
    out = [f'Fetched {fetched.strftime("%Y-%m-%d %H:%M")} UTC, covering the previous 36 hours.', '']
    for title, domain, link, _seen in items:
        out.append(f'- [{md(title)}]({url(link)}) ({md(domain)})')
    return out


def candidate_lines(today, path, ai_path=AI):
    # Pending candidates first reported today or yesterday (a candidate is dated
    # by its earliest report, which can be the day before the fetch).
    days = {today.isoformat(), (today - timedelta(days=1)).isoformat()}
    rows = [r for r in read_candidates(path)
            if r['status'] == 'pending' and r['date_public'] in days]
    ai = ai_status(today, ai_path)
    out = ['## Event screen', '']
    if ai is not None:
        out.append(f'AI screen ({ai.get("provider", "")} {ai["model"]}) read {ai["headlines"]} relevant headlines; '
                   f'every result is checked by code (region, cited headlines, 2+ sites).')
    else:
        out.append('AI screen unavailable today; the keyword screen was used '
                   '(an escalation word plus a region, 3+ sites).')
    out.append('')
    if rows:
        out += ['**Possible new events (need your approval):**', '']
        for r in rows:
            hint = f', may belong to episode {md(r["episode_hint"])}' if r['episode_hint'] else ''
            kind = f'{r.get("event_type")}, ' if r.get('event_type') else ''
            out.append(f'- `{md(r["candidate_id"])}`: [{md(r["title"])}]({url(r["source_url"])}) '
                       f'({md(kind)}{md(r["n_sites"])} sites{hint})')
        out += ['', 'To add one: GitHub, then Actions, then **approve-event**, then Run '
                'workflow, and paste the id.', '']
    else:
        out += ['No new conflict escalation found today.', '']
    if ai is not None and ai.get('notes'):
        out += ['**Also noted** (not conflict escalations, so no base rates yet):', '']
        for n in ai['notes']:
            out.append(f'- {md(n["title"])} ({md(n["event_type"]).replace("_", "-")}, '
                       f'{md(n["region"])}, [source]({url(n["url"])}))')
        out.append('')
    return out


def build(today, prices_dir=None, events_path=EVENTS, news_path=NEWS, recent_days=90,
          candidates_path=None, ai_path=None):
    candidates_path = candidates_path or CANDIDATES
    ai_path = ai_path or AI
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
        earlier = [e for e in catalog if e.date_public <= today]  # no future events
        latest = (f' Latest: {md(max(earlier, key=lambda e: e.date_public).title)} '
                  f'({max(e.date_public for e in earlier).isoformat()}).') if earlier else ''
        lines += [f'No catalog events in the last {recent_days} days.{latest}', '']
    for event in recent:
        comparable = [e for e in first_per_episode(catalog)
                      if e.episode != event.episode and e.date_public < event.date_public]
        lines += [f'### {md(event.title)} ({event.date_public.isoformat()})', '',
                  f'Source: {url(event.source_url)}', '']
        for asset_id in ('brent', 'wti', 'henry_hub', 'usd_nok'):
            if asset_id not in loaded:
                continue
            asset = BY_ID[asset_id]
            ctx = daily.event_context(event, comparable, loaded[asset_id])
            lines.append(f'**{asset.label}**: {ctx.days_since} trading days since the news, '
                         f'{pct(ctx.change_since)} since then. After comparable past events:')
            lines += [f'- {format_result(r, asset.label)}' for r in ctx.results]
            lines.append('')

    lines += candidate_lines(today, candidates_path, ai_path)
    lines += ['## Headlines (GDELT)', '']
    lines += news_lines(today, news_path)
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
