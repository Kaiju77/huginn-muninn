#!/usr/bin/env python3
"""Walk-forward backtest of the base rates; writes reports/calibration.md.

    python scripts/backtest.py [--entry after_news|before_news]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.assets import ASSETS  # noqa: E402
from src.huginn_muninn.calibration import (  # noqa: E402
    baseline_side_hits, bootstrap_diff, score, walk_forward)
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import DEFAULT_HORIZONS, ENTRY_RULES  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
OUT = ROOT / 'reports' / 'calibration.md'


def fmt(x):
    return 'n/a' if x is None else f'{x:.3f}'


UCDP_CATEGORY = 'mideast-conflict-ucdp'


def list_note(catalog):
    cats = {e.category for e in catalog}
    if cats == {UCDP_CATEGORY}:
        return ('This event list comes from a fixed rule applied to UCDP data, not hand-picking, '
                'so hindsight bias is smaller. But we chose the rule, and UCDP revises its death '
                'counts afterwards, so the selection still uses some later knowledge '
                '(see `src/huginn_muninn/ucdp_events.py`).')
    if cats == {'mideast-conflict'}:
        return ('The event list was picked by hand with hindsight (see `data/events/README.md`), '
                'which can make event base rates look better than they would be live.')
    return 'Check how this event list was made before trusting it.'



def build(entry='after_news', prices_dir=None, events_path=EVENTS):
    catalog = load_catalog(events_path)
    events = [e.to_event() for e in first_per_episode(catalog)]
    lines = ['# Is the tool right? Walk-forward backtest', '',
             f'Entry rule: `{entry}`. Each event is "predicted" from earlier events whose outcome '
             'was already known on its date, then scored against what happened. '
             'Brier score: lower is better; always saying 50% scores 0.250.', '',
             '| Asset | Horizon | Predictions | Side right: event / baseline | '
             'Brier: event | Brier: baseline | Difference (95% interval) |',
             '|---|---|---|---|---|---|---|']
    rows_n, comparisons = [], 0
    for asset in ASSETS:
        path = (prices_dir / f'{asset.asset_id}.csv') if prices_dir else asset.csv_path
        if not path.exists():
            continue
        closes = load_closes(path)
        for h in DEFAULT_HORIZONS:
            preds = walk_forward(events, closes, h, entry)
            s = score(preds, h)
            if s.n:
                rows_n.append(s.n)
                comparisons += 1
            if not s.n:
                lines.append(f'| {asset.label} | {h} days | 0 | | | | |')
                continue
            d = bootstrap_diff(preds)
            diff = 'n/a' if d is None else f'{d[0]:+.3f} ({d[1]:+.3f} to {d[2]:+.3f})'
            lines.append(f'| {asset.label} | {h} days | {s.n} | {s.hits} / {baseline_side_hits(preds)} | '
                         f'{fmt(s.brier_event)} | {fmt(s.brier_baseline)} | {diff} |')
    if not comparisons:
        return '\n'.join(lines + ['', 'Too few events (or no price files) to backtest: each '
                                   'prediction needs at least 8 earlier events with known outcomes.',
                                   '', '_Historical backtest, not a forecast or advice._', ''])
    lines += ['', '**How to read it.** Difference = event Brier minus baseline Brier; negative '
              'means the event base rate did better. Only an interval entirely below 0 is evidence '
              f'of skill, and even then: there are {comparisons} comparisons here, so one or two will '
              'look good by luck alone.', '',
              f'**Limits.** {min(rows_n, default=0)} to {max(rows_n, default=0)} predictions per '
              'row is very few. ' + list_note(catalog) + ' The live prediction log is the '
              'real test.', '',
              '_Historical backtest, not a forecast or advice._', '']
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--entry', choices=ENTRY_RULES, default='after_news')
    p.add_argument('--events', type=Path, default=EVENTS,
                   help='event catalog CSV (default: the hand-picked list)')
    a = p.parse_args(argv)
    if not a.events.is_file():
        p.error(f'no such event file: {a.events}')
    text = build(a.entry, events_path=a.events)
    # Another catalog never overwrites the main report.
    out = OUT if a.events.resolve() == EVENTS.resolve() else \
        OUT.with_name(f'calibration-{a.events.stem}.md')
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
