"""Live prediction log: the base rates the daily brief shows, scored later.

This is the live counterpart to the walk-forward backtest in
``calibration.py``. Each row is one base rate the brief showed for one recent
event, one asset and one horizon. It is recorded once, with only the data
available on the day it was made, and scored once its horizon has passed.

Pure functions, standard library only. No I/O here.

Rules:
- No look-ahead. ``record`` and ``score`` only look at closes on or before
  ``today``. A horizon whose outcome is already known on ``today`` is not
  recorded (it would not be a prediction).
- Same numbers as the brief: ``daily.event_context`` on the same comparables
  (``comparables``) with the same horizons and the ``after_news`` entry.
- A row is written once. A scored or void row is never changed.
"""

import csv
import io
from bisect import bisect_left
from datetime import date
from typing import NamedTuple, Optional

from src.huginn_muninn import daily
from src.huginn_muninn.calibration import brier
from src.huginn_muninn.catalog import first_per_episode
from src.huginn_muninn.study import AFTER_NEWS, DEFAULT_MAX_GAP_DAYS

HORIZONS = (5, 20, 60)                              # as in daily.event_context
BRIEF_ASSETS = ('brent', 'wti', 'henry_hub', 'usd_nok')  # as in scripts/daily_report.py
OPEN, SCORED, VOID = 'open', 'scored', 'void'


class Row(NamedTuple):
    made_on: date
    event_id: str
    asset_id: str
    horizon: int
    entry_rule: str
    n: int
    rises: int
    p_rose: Optional[float]      # None when too few comparable events
    ci_low: Optional[float]
    ci_high: Optional[float]
    median: Optional[float]
    low: Optional[float]         # range of comparable changes (project rule:
    high: Optional[float]        # every probability shown has n, CI and range)
    baseline_p: Optional[float]  # None when too few baseline windows
    baseline_n: int
    baseline_rises: int
    entry_date: Optional[date]
    entry_close: Optional[float]
    status: str
    exit_date: Optional[date] = None
    exit_close: Optional[float] = None
    change: Optional[float] = None
    rose: Optional[bool] = None
    scored_on: Optional[date] = None

    @property
    def key(self):
        return (self.event_id, self.asset_id, self.horizon, self.entry_rule)


COLUMNS = Row._fields


def comparables(catalog, event):
    """The comparables the brief uses: one event per episode, other episodes,
    strictly earlier public dates."""
    return [e for e in first_per_episode(catalog)
            if e.episode != event.episode and e.date_public < event.date_public]


def known_closes(closes, today):
    """Closes on or before ``today`` only."""
    return [c for c in closes if c.on <= today]


def entry_index(closes, day, max_gap_days=DEFAULT_MAX_GAP_DAYS):
    """Index of the ``after_news`` entry close, None if there is no close on or
    after ``day`` yet, or -1 if the first such close is more than
    ``max_gap_days`` later (the study skips such events)."""
    i = bisect_left([c.on for c in closes], day)
    if i >= len(closes):
        return None
    if (closes[i].on - day).days > max_gap_days:
        return -1
    return i


def record(existing_rows, today, recent_events, comparable_fn, closes_by_asset,
           horizons=HORIZONS, assets=BRIEF_ASSETS):
    """Rows plus one new open row per (event, asset, horizon, entry rule) not
    already present. Returns a new sorted list.

    Skipped (tried again on a later day): no entry close yet. Not recorded at
    all: the outcome is already known on ``today`` (exit close published), or
    the event has a public date after ``today``. Recorded as void: the first
    close after the news is more than the study's max gap later, so the study
    would never score it.
    """
    rows = list(existing_rows)
    have = {r.key for r in rows}
    for event in recent_events:
        if event.date_public > today:
            continue
        comparable = comparable_fn(event)
        for asset_id in assets:
            if asset_id not in closes_by_asset:
                continue
            closes = known_closes(closes_by_asset[asset_id], today)
            if len(closes) < 2:      # the brief skips such assets too
                continue
            i = entry_index(closes, event.date_public)
            if i is None:
                continue
            ctx = daily.event_context(event, comparable, closes, horizons)
            for res in ctx.results:
                key = (event.event_id, asset_id, res.horizon, AFTER_NEWS)
                if key in have:
                    continue
                if i >= 0 and i + res.horizon < len(closes):
                    continue         # outcome already known: not a prediction
                s, b = res.events, res.baseline
                entry = closes[i] if i >= 0 else None
                rows.append(Row(
                    today, event.event_id, asset_id, res.horizon, AFTER_NEWS,
                    s.n, s.rises, s.share, s.ci_low, s.ci_high, s.median, s.low, s.high,
                    b.share, b.n, b.rises,
                    entry.on if entry else None, entry.value if entry else None,
                    OPEN if entry else VOID,
                    scored_on=None if entry else today))
                have.add(key)
    return sorted(rows, key=sort_key)


def sort_key(row):
    return (row.made_on, row.event_id, row.asset_id, row.horizon, row.entry_rule)


def score(rows, closes_by_asset, today):
    """Score open rows whose exit close (``horizon`` trading days after the
    entry) is on or before ``today``. Non-positive entry or exit close: void.
    Scored and void rows are returned unchanged."""
    out = []
    for r in rows:
        if r.status != OPEN or r.asset_id not in closes_by_asset:
            out.append(r)
            continue
        if r.entry_close is not None and r.entry_close <= 0:
            out.append(r._replace(status=VOID, scored_on=today))
            continue
        closes = known_closes(closes_by_asset[r.asset_id], today)
        dates = [c.on for c in closes]
        i = bisect_left(dates, r.entry_date)
        if i >= len(closes) or dates[i] != r.entry_date:
            out.append(r)            # entry close missing from the series: leave open
            continue
        j = i + r.horizon
        if j >= len(closes):
            out.append(r)
            continue
        exit_ = closes[j]
        if exit_.value <= 0:
            out.append(r._replace(status=VOID, exit_date=exit_.on, exit_close=exit_.value,
                                  scored_on=today))
            continue
        change = exit_.value / r.entry_close - 1
        out.append(r._replace(status=SCORED, exit_date=exit_.on, exit_close=exit_.value,
                              change=change, rose=change > 0, scored_on=today))
    return out


class AssetScore(NamedTuple):
    asset_id: str
    horizon: int
    scored: int
    with_p: int                  # scored rows that had a probability
    brier_event: Optional[float]
    brier_baseline: Optional[float]  # on the same rows, where a baseline exists
    hits: int                    # p_rose >= 0.5 means "rise"; side was right


def summary(rows):
    """Per (asset, horizon): scored rows, rows with a probability, Brier of
    p_rose, Brier of baseline_p on those same rows, and side hits."""
    groups = {}
    for r in rows:
        if r.status == SCORED:
            groups.setdefault((r.asset_id, r.horizon), []).append(r)
    out = []
    for (asset_id, horizon), rs in sorted(groups.items()):
        with_p = [r for r in rs if r.p_rose is not None]
        out.append(AssetScore(
            asset_id, horizon, len(rs), len(with_p),
            brier([(r.p_rose, r.rose) for r in with_p]),
            brier([(r.baseline_p, r.rose) for r in with_p]),
            sum(1 for r in with_p if (r.p_rose >= 0.5) == r.rose)))
    return out


# CSV round trip. Empty cell = None. Floats use repr so they round-trip exactly.

def _cell(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    return str(value)


def to_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(COLUMNS)
    for r in sorted(rows, key=sort_key):
        w.writerow([_cell(v) for v in r])
    return buf.getvalue()


_DATES = ('made_on', 'entry_date', 'exit_date', 'scored_on')
_INTS = ('horizon', 'n', 'rises', 'baseline_n', 'baseline_rises')
_FLOATS = ('p_rose', 'ci_low', 'ci_high', 'median', 'low', 'high', 'baseline_p', 'entry_close',
           'exit_close', 'change')


def from_csv(text):
    reader = csv.DictReader(io.StringIO(text), strict=True)
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise ValueError(f'prediction log columns must be {",".join(COLUMNS)}')
    rows = []
    for raw in reader:
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError(f'prediction log line {reader.line_num}: expected {len(COLUMNS)} fields')
        try:
            values = {}
            for k, v in raw.items():
                if v == '':
                    values[k] = None
                elif k in _DATES:
                    values[k] = date.fromisoformat(v)
                elif k in _INTS:
                    values[k] = int(v)
                elif k in _FLOATS:
                    values[k] = float(v)
                elif k == 'rose':
                    if v not in ('yes', 'no'):
                        raise ValueError(v)
                    values[k] = v == 'yes'
                else:
                    values[k] = v
        except ValueError:
            raise ValueError(f'prediction log line {reader.line_num}: bad value') from None
        if values['status'] not in (OPEN, SCORED, VOID):
            raise ValueError(f'prediction log line {reader.line_num}: bad status')
        rows.append(Row(**values))
    keys = [r.key for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('prediction log has duplicate rows')
    return rows
