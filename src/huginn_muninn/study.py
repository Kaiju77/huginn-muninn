"""Event study: what did a price do after comparable past events?

Pure functions, standard library only. No fetching, no I/O.

Rules (see PROJECT_STATE.md):
- No look-ahead. Two entry rules, chosen per study:
  ``after_news`` (default): first close on or after the public date, the
  earliest price you could act on. Must fall within ``max_gap_days``.
  ``before_news``: last close strictly before the public date, which also
  captures the first reaction. Used to measure the reaction, not as a
  tradeable result.
- Every share comes with n, a Wilson 95% interval, median and range.
- Below ``min_n`` comparable events no share is reported. ``min_n`` can be
  raised but never set below 8.
- Each horizon is compared with the unconditional baseline: non-overlapping
  windows of the same length in the same price history, so the baseline's
  Wilson interval is not overstated by overlapping samples.
"""

from bisect import bisect_left
from datetime import date
from math import isfinite, sqrt
from statistics import median
from typing import NamedTuple, Optional, Sequence

DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_MIN_N = 8
AFTER_NEWS = 'after_news'
BEFORE_NEWS = 'before_news'
ENTRY_RULES = (AFTER_NEWS, BEFORE_NEWS)
DEFAULT_MAX_GAP_DAYS = 5
Z_95 = 1.959963984540054


class Close(NamedTuple):
    on: date
    value: float


class Event(NamedTuple):
    event_id: str
    date_public: date
    title: str = ''


class EventReturn(NamedTuple):
    event_id: str
    entry_date: date
    exit_date: date
    change: float  # fractional, 0.042 means +4.2%


class Summary(NamedTuple):
    n: int
    rises: int
    share: Optional[float]  # None when n < min_n
    ci_low: Optional[float]
    ci_high: Optional[float]
    median: Optional[float]
    low: Optional[float]
    high: Optional[float]
    too_few: bool


class HorizonResult(NamedTuple):
    horizon: int
    events: Summary
    baseline: Summary
    returns: tuple
    skipped: tuple  # (event_id, reason)


def sorted_closes(closes: Sequence[Close]) -> list:
    """Return closes sorted by date. Duplicate dates are an error."""
    for c in closes:
        if not isfinite(c.value):
            raise ValueError(f'non-finite close on {c.on.isoformat()}')
    ordered = sorted(closes, key=lambda c: c.on)
    for before, after in zip(ordered, ordered[1:]):
        if before.on == after.on:
            raise ValueError(f'duplicate close on {after.on.isoformat()}')
    return ordered


def wilson_interval(rises: int, n: int, z: float = Z_95):
    """Wilson score interval for rises/n. Returns (low, high)."""
    if n <= 0:
        raise ValueError('n must be positive')
    if not 0 <= rises <= n:
        raise ValueError('rises must be between 0 and n')
    p = rises / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if rises == 0 else max(0.0, centre - half)
    high = 1.0 if rises == n else min(1.0, centre + half)
    return low, high


def summarize(changes: Sequence[float], min_n: int = DEFAULT_MIN_N) -> Summary:
    """Summarize fractional changes. A rise is a change strictly above 0."""
    if min_n < DEFAULT_MIN_N:
        raise ValueError(f'min_n cannot be below {DEFAULT_MIN_N}')
    changes = list(changes)
    if not all(isfinite(c) for c in changes):
        raise ValueError('non-finite change')
    n = len(changes)
    if n == 0:
        return Summary(0, 0, None, None, None, None, None, None, True)
    rises = sum(1 for c in changes if c > 0)
    mid, low, high = median(changes), min(changes), max(changes)
    if n < min_n:
        return Summary(n, rises, None, None, None, mid, low, high, True)
    ci_low, ci_high = wilson_interval(rises, n)
    return Summary(n, rises, rises / n, ci_low, ci_high, mid, low, high, False)


def event_return(
    closes: Sequence[Close],
    event: Event,
    horizon: int,
    entry: str = AFTER_NEWS,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
):
    """Return (EventReturn, None) or (None, reason).

    ``closes`` must already be sorted (use ``sorted_closes``).
    """
    _check_horizon(horizon)
    _check_entry(entry)
    dates = [c.on for c in closes]
    first_on_or_after = bisect_left(dates, event.date_public)
    if entry == AFTER_NEWS:
        entry_index = first_on_or_after
        if entry_index >= len(closes):
            return None, 'no close on or after the event date'
        if (dates[entry_index] - event.date_public).days > max_gap_days:
            return None, f'no close within {max_gap_days} days after the event date'
    else:
        entry_index = first_on_or_after - 1
        if entry_index < 0:
            return None, 'no close before the event date'
        if (event.date_public - dates[entry_index]).days > max_gap_days:
            return None, f'no close within {max_gap_days} days before the event date'
    exit_index = entry_index + horizon
    if exit_index >= len(closes):
        return None, 'not enough closes after the event'
    entry, exit_ = closes[entry_index], closes[exit_index]
    if entry.value <= 0:
        return None, 'entry close is not positive'
    change = exit_.value / entry.value - 1
    return EventReturn(event.event_id, entry.on, exit_.on, change), None


def baseline_changes(closes: Sequence[Close], horizon: int, last_start=None) -> list:
    """Non-overlapping horizon-length changes: windows start at index 0,
    horizon, 2*horizon, ... A window is kept only if its start date is on or
    before ``last_start`` (when given) and its start close is positive.
    ``closes`` must already be sorted.
    """
    _check_horizon(horizon)
    changes = []
    for i in range(0, len(closes) - horizon, horizon):
        start = closes[i]
        if last_start is not None and start.on > last_start:
            break
        if start.value <= 0:
            continue
        changes.append(closes[i + horizon].value / start.value - 1)
    return changes


def _check_entry(entry):
    if entry not in ENTRY_RULES:
        raise ValueError(f'entry must be one of {ENTRY_RULES}, got {entry!r}')


def _check_horizon(horizon):
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise ValueError(f'horizon must be a whole number of at least 1, got {horizon!r}')


def run_study(
    events: Sequence[Event],
    closes: Sequence[Close],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    min_n: int = DEFAULT_MIN_N,
    era: Optional[tuple] = None,
    entry: str = AFTER_NEWS,
) -> list:
    """Run the event study for each horizon.

    ``era`` is an optional (start, end) date pair, inclusive. It selects the
    events by public date and the baseline windows by start date. An event's
    exit may fall after the era end; cutting the history would silently drop
    late events.
    """
    if min_n < DEFAULT_MIN_N:
        raise ValueError(f'min_n cannot be below {DEFAULT_MIN_N}')
    horizons = tuple(horizons)
    if not horizons:
        raise ValueError('at least one horizon is required')
    for horizon in horizons:
        _check_horizon(horizon)
    _check_entry(entry)
    ordered = sorted_closes(closes)
    chosen = list(events)
    base, last_start = ordered, None
    if era is not None:
        start, last_start = era
        chosen = [e for e in chosen if start <= e.date_public <= last_start]
        base = [c for c in ordered if c.on >= start]
    ids = [e.event_id for e in chosen]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate event_id')
    results = []
    for horizon in horizons:
        returns, skipped = [], []
        for event in chosen:
            result, reason = event_return(ordered, event, horizon, entry)
            if result is None:
                skipped.append((event.event_id, reason))
            else:
                returns.append(result)
        results.append(HorizonResult(
            horizon,
            summarize([r.change for r in returns], min_n),
            summarize(baseline_changes(base, horizon, last_start), min_n),
            tuple(returns),
            tuple(skipped),
        ))
    return results


def _pct(x: float) -> str:
    return f'{x * 100:+.1f}%'


def format_result(result: HorizonResult, asset: str = 'the asset') -> str:
    """One plain-language line per horizon."""
    s, b = result.events, result.baseline
    days = f'{result.horizon} trading days'
    if s.n == 0:
        return f'{days}: no comparable events with enough price history.'
    if s.too_few:
        return (
            f'{days}: too few comparable events (n={s.n}, need more). '
            f'Median {_pct(s.median)}, range {_pct(s.low)} to {_pct(s.high)}.'
        )
    line = (
        f'{days}: in {s.n} comparable events, {asset} rose in {s.rises} '
        f'({s.share * 100:.0f}%, 95% CI {s.ci_low * 100:.0f}-{s.ci_high * 100:.0f}%). '
        f'Median {_pct(s.median)}, range {_pct(s.low)} to {_pct(s.high)}.'
    )
    if b.share is not None:
        line += (
            f' Baseline: {b.n} non-overlapping {result.horizon}-day windows, '
            f'{b.rises} rose ({b.share * 100:.0f}%, 95% CI '
            f'{b.ci_low * 100:.0f}-{b.ci_high * 100:.0f}%), median {_pct(b.median)}, '
            f'range {_pct(b.low)} to {_pct(b.high)}.'
        )
    else:
        line += f' Baseline: too few windows (n={b.n}).'
    return line


def event_path(
    closes: Sequence[Close],
    event: Event,
    days: int = 60,
    entry: str = AFTER_NEWS,
    max_gap_days: int = DEFAULT_MAX_GAP_DAYS,
):
    """Return [(trading_day, change)] from the entry close for up to ``days``
    trading days, or None when there is no valid entry. Day 0 is the entry
    (change 0.0). Uses the same entry rule as ``event_return``. For charts.
    """
    first, reason = event_return(closes, event, 1, entry, max_gap_days)
    if first is None and 'not enough closes' not in reason:
        return None
    dates = [c.on for c in closes]
    start = bisect_left(dates, event.date_public)
    if entry == BEFORE_NEWS:
        start -= 1
    if start < 0 or start >= len(closes) or closes[start].value <= 0:
        return None
    base = closes[start].value
    end = min(len(closes) - 1, start + days)
    return [(i - start, closes[i].value / base - 1) for i in range(start, end + 1)]
