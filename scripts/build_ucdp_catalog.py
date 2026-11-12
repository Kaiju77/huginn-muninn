#!/usr/bin/env python3
"""Build data/events/mideast-conflict-ucdp.csv from data/ucdp/ged_mideast.csv.

    python scripts/build_ucdp_catalog.py
    python scripts/build_ucdp_catalog.py --threshold 50 --calm-days 180

The onset rule and its defaults are documented in
src/huginn_muninn/ucdp_events.py. The output uses the catalog schema and
is checked with catalog.load_catalog before it replaces the old file.
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fetch_ucdp import OUT as GED_CSV, read_ged_csv  # noqa: E402
from src.huginn_muninn.catalog import COLUMNS, first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.ucdp_events import CATEGORY, OnsetRule, find_onsets, to_catalog_rows  # noqa: E402

OUT = ROOT / 'data' / 'events' / 'mideast-conflict-ucdp.csv'


def write_catalog(rows, out, today):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        events = load_catalog(tmp, category=CATEGORY, today=today)
    except ValueError:
        tmp.unlink()
        raise
    tmp.replace(out)
    return events


def main(argv=None, src=GED_CSV, out=OUT, today=None):
    d = OnsetRule()
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--window-days', type=int, default=d.window_days)
    parser.add_argument('--threshold', type=int, default=d.threshold)
    parser.add_argument('--calm-days', type=int, default=d.calm_days)
    parser.add_argument('--types', default=','.join(map(str, d.types)))
    parser.add_argument('--max-date-prec', type=int, default=d.max_date_prec)
    parser.add_argument('--anchor', default=d.anchor, choices=('date_start', 'date_end'))
    parser.add_argument('--lag-days', type=int, default=d.lag_days)
    parser.add_argument('--merge-days', type=int, default=d.merge_days)
    parser.add_argument('--version', default='', help='GED version, written into notes')
    args = parser.parse_args(argv)
    today = today or date.today()
    try:
        rule = OnsetRule(args.window_days, args.threshold, args.calm_days,
                         tuple(int(t) for t in args.types.split(',') if t.strip()),
                         args.max_date_prec, args.anchor, args.lag_days, args.merge_days)
        rule.check()
        ged = read_ged_csv(src)
        onsets = find_onsets(ged, rule)
        rows = to_catalog_rows(onsets, rule, today, args.version)
        if not rows:
            raise ValueError('the rule found no onsets; old catalog kept')
        events = write_catalog(rows, out, today)
    except (OSError, ValueError) as err:
        print(f'ucdp catalog: not written ({err})', file=sys.stderr)
        return 1
    per_country = Counter(e.region for e in events)
    print(f'ucdp catalog: {len(ged)} GED rows -> {len(events)} onsets in '
          f'{len(first_per_episode(events))} episodes, {events[0].date_public} to '
          f'{events[-1].date_public}')
    print(f'  {rule.describe()}; merge={rule.merge_days}d')
    for country, n in sorted(per_country.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f'  {country}: {n}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
