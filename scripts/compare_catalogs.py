#!/usr/bin/env python3
"""Hand-picked vs rule-based (UCDP) crisis lists, side by side.

    python scripts/compare_catalogs.py     # writes reports/catalog-comparison.md

Skips cleanly (exit 0, short report) until data/events/mideast-conflict-ucdp.csv
exists; that file is built weekly by the fetch-ucdp workflow.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest import build as backtest_build  # noqa: E402
from src.huginn_muninn.assets import ASSETS  # noqa: E402
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.compare import match_events  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import format_result, run_study  # noqa: E402

HAND = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
UCDP = ROOT / 'data' / 'events' / 'mideast-conflict-ucdp.csv'
OUT = ROOT / 'reports' / 'catalog-comparison.md'
DISCLAIMER = '_Historical base rates, not a forecast or advice._'


def study_lines(events, prices_dir=None):
    out = []
    for asset in ASSETS:
        path = (prices_dir / f'{asset.asset_id}.csv') if prices_dir else asset.csv_path
        if not path.exists():
            continue
        closes = load_closes(path)
        out.append(f'**{asset.label}**')
        out += [f'- {format_result(r, asset.label)}'
                for r in run_study([e.to_event() for e in events], closes)]
        out.append('')
    return out


def build(hand_path=HAND, ucdp_path=UCDP, prices_dir=None):
    lines = ['# Crisis lists compared: hand-picked vs rule-based (UCDP)', '', DISCLAIMER, '']
    if not ucdp_path.exists():
        return '\n'.join(lines + [
            'The rule-based list does not exist yet. It is built by the weekly `fetch-ucdp` '
            'workflow once the repository secret `UCDP_TOKEN` is set.', ''])
    hand = first_per_episode(load_catalog(hand_path))
    ucdp = first_per_episode(load_catalog(ucdp_path))
    matches, hand_only, ucdp_only = match_events(hand, ucdp)
    lines += [
        f'Independent crises (one per episode): hand-picked {len(hand)}, rule-based {len(ucdp)}. '
        f'Within 7 days of each other: {len(matches)}.', '',
        'Agreement matters: hand-picked crises that the rule also finds were not just picked '
        'because oil moved. Hand-picked crises the rule misses are often oil-specific '
        '(tanker attacks, few deaths); rule-only crises are often local wars with little oil '
        'relevance. Neither list is "right"; the comparison shows how much the choice matters.', '',
        '## Matched', '', '| Hand-picked | Rule-based | Days apart |', '|---|---|---|']
    lines += [f'| {m.hand_id} ({m.hand_date}) | {m.ucdp_id} ({m.ucdp_date}) | {m.days_apart} |'
              for m in matches]
    lines += ['', f'## Only hand-picked ({len(hand_only)})', '']
    lines += [f'- {e.event_id} ({e.date_public}): {e.title}' for e in hand_only]
    lines += ['', f'## Only rule-based ({len(ucdp_only)})', '']
    lines += [f'- {e.event_id} ({e.date_public}): {e.title}' for e in ucdp_only[:60]]
    if len(ucdp_only) > 60:
        lines.append(f'- … and {len(ucdp_only) - 60} more')
    lines += ['', '## Base rates, hand-picked list', ''] + study_lines(hand, prices_dir)
    lines += ['## Base rates, rule-based list', ''] + study_lines(ucdp, prices_dir)
    lines += ['## Backtest, rule-based list', '']
    lines += backtest_build(prices_dir=prices_dir, events_path=ucdp_path).split('\n')[2:]
    return '\n'.join(lines)


def main():
    text = build()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(text, encoding='utf-8')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
