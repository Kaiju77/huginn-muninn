#!/usr/bin/env python3
"""Run the event study for every asset with a price file and print the results.

    python scripts/event_study.py
    python scripts/event_study.py --assets brent wti --entry before_news
    python scripts/event_study.py --era 2015-01-01:2026-12-31
"""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.assets import ASSETS, BY_ID  # noqa: E402
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import ENTRY_RULES, format_result, run_study  # noqa: E402


def parse_era(text):
    start, end = text.split(':')
    return date.fromisoformat(start), date.fromisoformat(end)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--events', type=Path, default=ROOT / 'data/events/mideast-conflict.csv')
    p.add_argument('--assets', nargs='*', choices=sorted(BY_ID))
    p.add_argument('--prices-dir', type=Path, help='read <asset>.csv from here instead')
    p.add_argument('--entry', choices=ENTRY_RULES, default='after_news')
    p.add_argument('--era', type=parse_era)
    p.add_argument('--all-events', action='store_true',
                   help='count every event, not one per episode')
    a = p.parse_args(argv)
    catalog = load_catalog(a.events)
    chosen = catalog if a.all_events else first_per_episode(catalog)
    events = [e.to_event() for e in chosen]
    assets = [BY_ID[i] for i in a.assets] if a.assets else list(ASSETS)
    print(f'{len(chosen)} events ({len(catalog)} in catalog), entry {a.entry}'
          + (f', era {a.era[0]} to {a.era[1]}' if a.era else ''))
    for asset in assets:
        path = (a.prices_dir / f'{asset.asset_id}.csv') if a.prices_dir else asset.csv_path
        if not path.exists():
            print(f'\n{asset.label}: no price file yet ({path.name}).')
            continue
        closes = load_closes(path)
        print(f'\n{asset.label} ({asset.unit}), prices {closes[0].on} to {closes[-1].on}')
        for result in run_study(events, closes, entry=a.entry, era=a.era):
            print(format_result(result, asset.label))
            for event_id, reason in result.skipped:
                print(f'  skipped {event_id}: {reason}')
    print('\nHistorical base rates, not a forecast or advice.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
