#!/usr/bin/env python3
"""Hand-picked vs rule-based (UCDP) crisis lists, side by side.

    python scripts/compare_catalogs.py     # writes reports/catalog-comparison.md

Skips cleanly (exit 0, short report) until data/events/mideast-conflict-ucdp.csv
exists; that file is built weekly by the fetch-ucdp workflow.
"""

import re
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest import build as backtest_build  # noqa: E402
from src.huginn_muninn.assets import ASSETS  # noqa: E402
from src.huginn_muninn.catalog import load_catalog  # noqa: E402
from src.huginn_muninn.compare import (  # noqa: E402
    chance_matches, coverage_window, episodes, in_window, match_episodes)
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import format_result, run_study  # noqa: E402
from src.huginn_muninn.ucdp_events import OnsetRule  # noqa: E402

HAND = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
UCDP = ROOT / 'data' / 'events' / 'mideast-conflict-ucdp.csv'
GED = ROOT / 'data' / 'ucdp' / 'ged_mideast.csv'
OUT = ROOT / 'reports' / 'catalog-comparison.md'
DISCLAIMER = '_Historical base rates, not a forecast or advice._'


def md(text):
    """Catalog text made safe for one markdown line or table cell."""
    text = re.sub(r'\s+', ' ', str(text)).strip()
    text = text.replace('|', '/').replace('<', '&lt;').replace('`', "'")
    return text.lstrip('#>-*+ ') or '?'


def ged_end(ged_path, ucdp_events, rule):
    """Last day of GED data: from the GED download if present, else the last onset."""
    if Path(ged_path).exists():
        from scripts.fetch_ucdp import read_ged_csv
        rows = read_ged_csv(ged_path)
        if rows:
            return max(r.date_end for r in rows)
    return max(e.date_public for e in ucdp_events) - timedelta(days=rule.lag_days)


def study_lines(openers, prices_dir=None):
    out, found = [], False
    for asset in ASSETS:
        path = (prices_dir / f'{asset.asset_id}.csv') if prices_dir else asset.csv_path
        if not path.exists():
            continue
        found = True
        closes = load_closes(path)
        out.append(f'**{asset.label}**')
        out += [f'- {format_result(r, asset.label)}'
                for r in run_study([e.to_event() for e in openers], closes)]
        out.append('')
    return out if found else ['No price files found.', '']


def missing(text):
    return '\n'.join(['# Crisis lists compared: hand-picked vs rule-based (UCDP)', '',
                      DISCLAIMER, '', text, ''])


def build(hand_path=HAND, ucdp_path=UCDP, prices_dir=None, ged_path=GED, rule=OnsetRule()):
    if not Path(ucdp_path).exists():
        return missing('The rule-based list does not exist yet. It is built by the weekly '
                       '`fetch-ucdp` workflow once the repository secret `UCDP_TOKEN` is set.')
    ucdp_events = load_catalog(ucdp_path)
    if not ucdp_events:
        return missing('The rule-based list is empty: the rule found no onsets in the UCDP data.')
    start, end = coverage_window(rule, ged_end(ged_path, ucdp_events, rule))
    hand_all, ucdp_all = episodes(load_catalog(hand_path)), episodes(ucdp_events)
    hand, hand_out = in_window(hand_all, start, end)
    ucdp, _ = in_window(ucdp_all, start, end)
    matches, hand_only, ucdp_only = match_episodes(hand, ucdp)
    luck = chance_matches(hand, ucdp)
    lines = [
        '# Crisis lists compared: hand-picked vs rule-based (UCDP)', '', DISCLAIMER, '',
        f'Compared period (what UCDP data covers): {start} to {end}. '
        f'Crises (one per episode) in that period: hand-picked {len(hand)}, rule-based {len(ucdp)}.', '',
        f'Agreements (same country, within 7 days): **{len(matches)}**. With the UCDP dates moved '
        f'2-12 months, the same test still finds {luck:.1f} on average, so that many agreements '
        'come from luck alone.', '',
        'Hand-picked crises the rule misses are often oil-specific (tanker attacks, few deaths). '
        'Rule-only crises are often local wars with little oil relevance. Neither list is "right"; '
        'the comparison shows how much the choice of list changes the base rates.', '',
        '## Agreements', '', '| Hand-picked | Rule-based | Days apart |', '|---|---|---|']
    lines += [f'| {md(m.hand_event.event_id)} ({m.hand_event.date_public}) | '
              f'{md(m.ucdp_event.event_id)} ({m.ucdp_event.date_public}) | {m.days_apart} |'
              for m in matches]
    lines += ['', f'## Only hand-picked ({len(hand_only)})', '']
    lines += [f'- {md(e.opener.event_id)} ({e.start}): {md(e.opener.title)}' for e in hand_only]
    lines += ['', f'## Only rule-based ({len(ucdp_only)})', '']
    lines += [f'- {md(e.opener.event_id)} ({e.start}): {md(e.opener.title)}' for e in ucdp_only[:60]]
    if len(ucdp_only) > 60:
        lines.append(f'- … and {len(ucdp_only) - 60} more')
    if hand_out:
        lines += ['', f'## Hand-picked, outside UCDP coverage ({len(hand_out)}, not compared)', '']
        lines += [f'- {md(e.opener.event_id)} ({e.start}): {md(e.opener.title)}' for e in hand_out]
    lines += ['', '## Base rates, hand-picked list (all years)', '']
    lines += study_lines([e.opener for e in hand_all], prices_dir)
    lines += [f'## Base rates, rule-based list ({start.year}-{end.year})', '']
    lines += study_lines([e.opener for e in ucdp_all], prices_dir)
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
