"""Is the tool right? Walk-forward backtest and Brier scores.

For every catalog event, in date order, the "prediction" is the share of
earlier comparable events whose outcome was already known on that date
(their exit close is before the event's public date). It is then scored
against what actually happened. The same is done for the naive baseline
(share of earlier non-overlapping windows that rose), so we can see whether
event base rates beat "markets usually rise".

Brier score: mean of (predicted probability - outcome)^2. Lower is better.
0.25 is what always saying 50% scores.
"""

import random
from bisect import bisect_left
from typing import NamedTuple, Optional

from src.huginn_muninn.study import (
    AFTER_NEWS, DEFAULT_MIN_N, baseline_changes, event_return, wilson_interval,
)


class Prediction(NamedTuple):
    event_id: str
    horizon: int
    n: int                 # earlier events with a known outcome
    p_event: float         # share of those that rose
    p_baseline: Optional[float]
    rose: bool             # what actually happened
    change: float


def walk_forward(events, closes, horizon, entry=AFTER_NEWS, min_n=DEFAULT_MIN_N):
    """Predictions for every event that has at least ``min_n`` earlier events
    with known outcomes and its own outcome available. ``events`` should be
    one per episode (independent)."""
    outcomes = []
    for e in sorted(events, key=lambda e: e.date_public):
        r, _ = event_return(closes, e, horizon, entry)
        outcomes.append((e, r))
    dates = [c.on for c in closes]
    preds = []
    for e, r in outcomes:
        if r is None:
            continue
        known = [o for _, o in outcomes
                 if o is not None and o.event_id != e.event_id and o.exit_date < e.date_public]
        if len(known) < min_n:
            continue
        cut = bisect_left(dates, e.date_public)  # closes strictly before the news
        base = baseline_changes(closes[:cut], horizon)
        p_base = sum(1 for c in base if c > 0) / len(base) if base else None
        preds.append(Prediction(e.event_id, horizon, len(known),
                                sum(1 for o in known if o.change > 0) / len(known),
                                p_base, r.change > 0, r.change))
    return preds


def brier(pairs):
    pairs = [(p, y) for p, y in pairs if p is not None]
    if not pairs:
        return None
    return sum((p - (1.0 if y else 0.0)) ** 2 for p, y in pairs) / len(pairs)


class Score(NamedTuple):
    horizon: int
    n: int
    hits: int                 # predicted side (p>=0.5 means "rise") was right
    brier_event: Optional[float]
    brier_baseline: Optional[float]
    brier_coin: Optional[float]
    rose: int
    rose_ci: Optional[tuple]


def score(preds, horizon):
    if not preds:
        return Score(horizon, 0, 0, None, None, None, 0, None)
    rose = sum(1 for p in preds if p.rose)
    hits = sum(1 for p in preds if (p.p_event >= 0.5) == p.rose)
    return Score(horizon, len(preds), hits,
                 brier([(p.p_event, p.rose) for p in preds]),
                 brier([(p.p_baseline, p.rose) for p in preds]),
                 brier([(0.5, p.rose) for p in preds]),
                 rose, wilson_interval(rose, len(preds)))


def bootstrap_diff(preds, resamples=2000, seed=0):
    """Brier(event base rate) - Brier(baseline), with a 95% bootstrap interval.
    Negative means the event base rate did better. Returns (diff, low, high) or
    None when there are no predictions with a baseline."""
    pairs = [p for p in preds if p.p_baseline is not None]
    if not pairs:
        return None

    def diff(sample):
        return (brier([(p.p_event, p.rose) for p in sample])
                - brier([(p.p_baseline, p.rose) for p in sample]))

    rng = random.Random(seed)
    draws = sorted(diff([rng.choice(pairs) for _ in pairs]) for _ in range(resamples))
    return diff(pairs), draws[int(0.025 * resamples)], draws[int(0.975 * resamples) - 1]


def baseline_side_hits(preds):
    """How often the baseline's side (p >= 0.5 means rise) was right."""
    return sum(1 for p in preds if p.p_baseline is not None
               and (p.p_baseline >= 0.5) == p.rose)
