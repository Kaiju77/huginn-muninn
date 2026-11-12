#!/usr/bin/env python3
"""Record the base rates the daily brief shows and score them later.

    python scripts/prediction_log.py [--today 2026-11-12]

Reads data/prices/*.csv (closes on or before --today only) and the event
catalog, appends new predictions to data/predictions/log.csv, scores open
ones whose horizon has passed, and writes reports/prediction-log.md.
"""

import argparse
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn import daily, predictions as pr  # noqa: E402
from src.huginn_muninn.assets import ASSETS, BY_ID  # noqa: E402
from src.huginn_muninn.catalog import load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import wilson_interval  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
LOG = ROOT / 'data' / 'predictions' / 'log.csv'
REPORT = ROOT / 'reports' / 'prediction-log.md'
RECENT_DAYS = 90  # as in scripts/daily_report.py
CAVEAT = ('_Live log of historical base rates. Very few predictions so far, and rows for the '
          'same event (other assets, other horizons) are not independent. '
          'Not a forecast or advice. You make the decisions._')


def write_atomic(path, text):
    """Write ``text`` to ``path`` via a temp file in the same folder and
    os.replace, so a crash never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_log(path):
    path = Path(path)
    if not path.exists():
        write_atomic(path, pr.to_csv([]))
        return []
    return pr.from_csv(path.read_text(encoding='utf-8'))


def load_prices(today, prices_dir=None):
    out = {}
    for asset in ASSETS:
        path = (Path(prices_dir) / f'{asset.asset_id}.csv') if prices_dir else asset.csv_path
        if path.exists():
            out[asset.asset_id] = pr.known_closes(load_closes(path), today)
    return out


def pct(x, signed=True):
    if x is None:
        return 'n/a'
    return f'{x * 100:+.1f}%' if signed else f'{x * 100:.0f}%'


def label(asset_id):
    return BY_ID[asset_id].label if asset_id in BY_ID else asset_id


def base_rate(r):
    if r.p_rose is None:
        return f'too few (n={r.n})'
    return (f'{pct(r.p_rose, False)} (n={r.n}, {r.rises} rose, 95% CI '
            f'{pct(r.ci_low, False)}-{pct(r.ci_high, False)})')


def baseline(r):
    if r.baseline_p is None:
        return f'too few windows (n={r.baseline_n})'
    low, high = wilson_interval(r.baseline_rises, r.baseline_n)
    return (f'{pct(r.baseline_p, False)} (n={r.baseline_n} windows, 95% CI '
            f'{pct(low, False)}-{pct(high, False)})')


def spread(r):
    if r.median is None:
        return 'n/a'
    return f'median {pct(r.median)}, range {pct(r.low)} to {pct(r.high)}'


def fmt(x):
    return 'n/a' if x is None else f'{x:.3f}'


def report(rows, today):
    open_rows = [r for r in rows if r.status == pr.OPEN]
    scored = [r for r in rows if r.status == pr.SCORED]
    void = [r for r in rows if r.status == pr.VOID]
    lines = [f'# Prediction log, {today.isoformat()}', '', CAVEAT, '',
             'For each new crisis (the event that opens its episode; follow-ups in the same crisis '
             'are shown in the brief but not logged, so a crisis counts once), the brief\'s base '
             'rates are recorded once, with only the prices known that day, and scored when the '
             'horizon has passed. EIA publishes late, so a few closes after the entry may already '
             'be known when a row is recorded. '
             'This is the live test of the walk-forward backtest (`reports/calibration.md`).', '',
             f'{len(rows)} predictions: {len(open_rows)} open, {len(scored)} scored, '
             f'{len(void)} void.', '',
             '## Open predictions', '']
    if open_rows:
        lines += ['| Made on | Event | Asset | Horizon | Entry | P(rise), from comparables | '
                  'Comparable moves | Baseline P(rise) |',
                  '|---|---|---|---|---|---|---|---|']
        for r in open_rows:
            lines.append(f'| {r.made_on.isoformat()} | `{r.event_id}` | {label(r.asset_id)} | '
                         f'{r.horizon} days | {r.entry_date.isoformat()} at {r.entry_close:g} | '
                         f'{base_rate(r)} | {spread(r)} | {baseline(r)} |')
    else:
        lines.append('No open predictions.')
    lines += ['', '## Scored so far', '']
    stats = pr.summary(rows)
    if stats:
        lines += ['| Asset | Horizon | Scored | With a probability | Side right | '
                  'Brier: event | Brier: baseline |',
                  '|---|---|---|---|---|---|---|']
        for s in stats:
            lines.append(f'| {label(s.asset_id)} | {s.horizon} days | {s.scored} | {s.with_p} | '
                         f'{s.hits} of {s.with_p} | {fmt(s.brier_event)} | '
                         f'{fmt(s.brier_baseline)} |')
        lines += ['', 'Brier score: lower is better; always saying 50% scores 0.250. The baseline '
                  'column is scored on the same rows. Rows with "too few" comparables are scored '
                  'but left out of Brier and side counts.']
    else:
        lines.append('Nothing scored yet.')
    lines += ['', '**Limits.** With this few scored predictions, no difference between the event '
              'base rate and the baseline means anything yet. Several events in one crisis, and '
              'one event across assets and horizons, move together.', '']
    return '\n'.join(lines)


BACKFILL_BANNER = ('**BACKFILL, not live: uses a catalog picked with hindsight. Not evidence '
                   'of skill.**\n\n')


class BackfillRefused(ValueError):
    pass


def run(today, log_path=LOG, report_path=REPORT, prices_dir=None, events_path=EVENTS,
        allow_backfill=False, now=None):
    """Record and score. A live log only moves forward in real time: ``today``
    must be the actual UTC date and not before the newest row. Backfills
    (``allow_backfill``) must write to a separate file, never the live log,
    because they use a catalog picked with hindsight (review round 9)."""
    now = now or datetime.now(timezone.utc).date()
    rows = read_log(log_path)
    newest = max((r.made_on for r in rows), default=None)
    if newest is not None and today < newest:
        raise BackfillRefused(f'--today {today} is before the newest row ({newest})')
    if today != now and not allow_backfill:
        raise BackfillRefused(f'--today {today} is not today ({now}); use --backfill-to FILE')
    if allow_backfill and (Path(log_path).resolve() == LOG.resolve()
                           or Path(report_path).resolve() == REPORT.resolve()):
        raise BackfillRefused('a backfill must not write the live log or the live report')
    closes = load_prices(today, prices_dir)
    catalog = [e for e in load_catalog(events_path) if e.date_public <= today]
    recent = pr.first_of_episodes(daily.recent_events(catalog, today, RECENT_DAYS), catalog,
                                  {r.event_id for r in rows})
    rows = pr.record(rows, today, recent, lambda e: pr.comparables(catalog, e), closes)
    rows = pr.score(rows, closes, today)
    write_atomic(log_path, pr.to_csv(rows))
    text = report(rows, today)
    if allow_backfill:
        text = BACKFILL_BANNER + text
    write_atomic(report_path, text)
    return rows, text


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--today', type=date.fromisoformat,
                   default=datetime.now(timezone.utc).date())
    p.add_argument('--backfill-to', type=Path, metavar='FILE',
                   help='write a backfill (past --today) to FILE instead of the live log')
    a = p.parse_args(argv)
    try:
        if a.backfill_to:
            _rows, text = run(a.today, log_path=a.backfill_to,
                              report_path=a.backfill_to.with_suffix('.md'), allow_backfill=True)
        else:
            _rows, text = run(a.today)
    except BackfillRefused as err:
        print(f'Refused: {err}', file=sys.stderr)
        return 2
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
