#!/usr/bin/env python3
"""Run the event study and print one line per horizon.

    python scripts/event_study.py
    python scripts/event_study.py --entry before_news --era 2015-01-01:2026-12-31
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import ENTRY_RULES, format_result, run_study  # noqa: E402


def parse_era(text):
    start, end = text.split(':')
    return date.fromisoformat(start), date.fromisoformat(end)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--events', type=Path, default=ROOT / 'data/events/mideast-conflict.csv')
    p.add_argument('--prices', type=Path, default=ROOT / 'data/prices/brent_daily.csv')
    p.add_argument('--asset', default='Brent')
    p.add_argument('--entry', choices=ENTRY_RULES, default='after_news')
    p.add_argument('--era', type=parse_era)
    p.add_argument('--all-events', action='store_true',
                   help='count every event, not one per episode')
    a = p.parse_args(argv)
    catalog = load_catalog(a.events)
    chosen = catalog if a.all_events else first_per_episode(catalog)
    closes = load_closes(a.prices)
    print(f'{a.asset}: {len(chosen)} events ({len(catalog)} in catalog), '
          f'prices {closes[0].on} to {closes[-1].on}, entry {a.entry}'
          + (f', era {a.era[0]} to {a.era[1]}' if a.era else ''))
    for result in run_study([e.to_event() for e in chosen], closes, entry=a.entry, era=a.era):
        print(format_result(result, a.asset))
        for event_id, reason in result.skipped:
            print(f'  skipped {event_id}: {reason}')
    print('Historical base rates, not a forecast or advice.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
