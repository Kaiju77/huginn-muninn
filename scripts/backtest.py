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
from src.huginn_muninn.calibration import score, walk_forward  # noqa: E402
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import DEFAULT_HORIZONS, ENTRY_RULES  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
OUT = ROOT / 'reports' / 'calibration.md'


def fmt(x):
    return 'n/a' if x is None else f'{x:.3f}'


def build(entry='after_news', prices_dir=None, events_path=EVENTS):
    events = [e.to_event() for e in first_per_episode(load_catalog(events_path))]
    lines = ['# Is the tool right? Walk-forward backtest', '',
             f'Entry rule: `{entry}`. Each event is "predicted" from earlier events whose outcome '
             'was already known on its date, then scored against what happened. '
             'Brier score: lower is better; always saying 50% scores 0.250.', '',
             '| Asset | Horizon | Predictions | Side right | Brier: event base rate | '
             'Brier: normal-period baseline | Brier: 50% |',
             '|---|---|---|---|---|---|---|']
    for asset in ASSETS:
        path = (prices_dir / f'{asset.asset_id}.csv') if prices_dir else asset.csv_path
        if not path.exists():
            continue
        closes = load_closes(path)
        for h in DEFAULT_HORIZONS:
            s = score(walk_forward(events, closes, h, entry), h)
            side = f'{s.hits}/{s.n}' if s.n else '0'
            lines.append(f'| {asset.label} | {h} days | {s.n} | {side} | {fmt(s.brier_event)} | '
                         f'{fmt(s.brier_baseline)} | {fmt(s.brier_coin)} |')
    lines += ['', 'How to read it: the event base rate is only useful if its Brier score is '
              'clearly below both the baseline and 50%. With this few predictions, differences '
              'under about 0.03 are noise.', '',
              '_Historical backtest, not a forecast or advice._', '']
    return '\n'.join(lines)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--entry', choices=ENTRY_RULES, default='after_news')
    a = p.parse_args(argv)
    text = build(a.entry)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
