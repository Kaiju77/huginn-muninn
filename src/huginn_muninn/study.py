"""Event study: what did a price do after comparable past events?

Pure functions, standard library only. No fetching, no I/O.

Rules (see PROJECT_STATE.md):
- No look-ahead. Entry is the last close on or before the date the event
  became public. Only later closes are used for the exit.
- Every share comes with n, a Wilson 95% interval, median and range.
- Below ``min_n`` comparable events no share is reported.
- Each horizon is compared with the unconditional baseline: every window of
  the same length in the same price history.
"""

from bisect import bisect_right
from datetime import date
from math import sqrt
from statistics import median
from typing import NamedTuple, Optional, Sequence

DEFAULT_HORIZONS = (5, 20, 60)
DEFAULT_MIN_N = 8
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
    n = len(changes)
    if n == 0:
        return Summary(0, 0, None, None, None, None, None, None, True)
    rises = sum(1 for c in changes if c > 0)
    mid, low, high = median(changes), min(changes), max(changes)
    if n < min_n:
        return Summary(n, rises, None, None, None, mid, low, high, True)
    ci_low, ci_high = wilson_interval(rises, n)
    return Summary(n, rises, rises / n, ci_low, ci_high, mid, low, high, False)


def event_return(closes: Sequence[Close], event: Event, horizon: int):
    """Return (EventReturn, None) or (None, reason).

    ``closes`` must already be sorted (use ``sorted_closes``).
    """
    if horizon < 1:
        raise ValueError('horizon must be at least 1')
    dates = [c.on for c in closes]
    entry_index = bisect_right(dates, event.date_public) - 1
    if entry_index < 0:
        return None, 'no close on or before the event date'
    exit_index = entry_index + horizon
    if exit_index >= len(closes):
        return None, 'not enough closes after the event'
    entry, exit_ = closes[entry_index], closes[exit_index]
    if entry.value <= 0:
        return None, 'entry close is not positive'
    change = exit_.value / entry.value - 1
    return EventReturn(event.event_id, entry.on, exit_.on, change), None


def baseline_changes(closes: Sequence[Close], horizon: int) -> list:
    """Every horizon-length change in the history (overlapping windows)."""
    return [
        closes[i + horizon].value / closes[i].value - 1
        for i in range(len(closes) - horizon)
        if closes[i].value > 0
    ]


def _era_baseline(closes, horizon, starts):
    changes = baseline_changes(closes, horizon)
    return changes if starts is None else changes[:starts]


def run_study(
    events: Sequence[Event],
    closes: Sequence[Close],
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    min_n: int = DEFAULT_MIN_N,
    era: Optional[tuple] = None,
) -> list:
    """Run the event study for each horizon.

    ``era`` is an optional (start, end) date pair, inclusive. It selects the
    events by public date and the baseline windows by start date. An event's
    exit may fall after the era end; cutting the history would silently drop
    late events.
    """
    ordered = sorted_closes(closes)
    chosen = list(events)
    base = ordered
    if era is not None:
        start, end = era
        chosen = [e for e in chosen if start <= e.date_public <= end]
        base = [c for c in ordered if c.on >= start]
        cut = sum(1 for c in base if c.on <= end)
    ids = [e.event_id for e in chosen]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate event_id')
    results = []
    for horizon in horizons:
        returns, skipped = [], []
        for event in chosen:
            result, reason = event_return(ordered, event, horizon)
            if result is None:
                skipped.append((event.event_id, reason))
            else:
                returns.append(result)
        results.append(HorizonResult(
            horizon,
            summarize([r.change for r in returns], min_n),
            summarize(_era_baseline(base, horizon, cut if era else None), min_n),
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
            f' Baseline: any {result.horizon}-day window rose '
            f'{b.share * 100:.0f}% of the time, median {_pct(b.median)}.'
        )
    return line
