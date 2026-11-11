"""Pure functions for the daily report. No I/O here.

The report says what moved, how unusual the move was against the asset's own
history, which catalog events are recent and what history says after them,
and which headlines appeared. Headlines are context, not proof of cause.
"""

import re
from bisect import bisect_left

from src.huginn_muninn.candidates import regions_of
from typing import NamedTuple, Optional

from src.huginn_muninn.study import AFTER_NEWS, event_return, run_study


class Move(NamedTuple):
    label: str
    unit: str
    on: object          # date of the latest close
    close: float
    change_1d: Optional[float]
    change_5d: Optional[float]
    rank_1d: Optional[float]   # share of past days with a smaller absolute 1-day move


def move(label, unit, closes):
    """Latest close, 1- and 5-day change, and how unusual the 1-day move is."""
    last = closes[-1]

    def change(back):
        if len(closes) <= back or closes[-1 - back].value <= 0:
            return None
        return last.value / closes[-1 - back].value - 1

    c1 = change(1)
    rank = None
    if c1 is not None:
        history = sorted(
            abs(closes[i].value / closes[i - 1].value - 1)
            for i in range(1, len(closes) - 1)
            if closes[i - 1].value > 0
        )
        if history:
            rank = bisect_left(history, abs(c1)) / len(history)
    return Move(label, unit, last.on, last.value, c1, change(5), rank)


def recent_events(catalog_events, today, days=90):
    """Catalog events whose public date is within ``days`` calendar days."""
    return [e for e in catalog_events if 0 <= (today - e.date_public).days <= days]


class EventContext(NamedTuple):
    event: object
    days_since: int               # trading days since entry
    change_since: Optional[float]
    results: list                 # HorizonResult list for comparable events


def event_context(event, comparable, closes, horizons=(5, 20, 60)):
    """Where we are since ``event`` and the base rates of comparable events.
    ``comparable`` must not include ``event`` itself."""
    dates = [c.on for c in closes]
    entry = bisect_left(dates, event.date_public)
    days_since, change_since = 0, None
    if entry < len(closes) and closes[entry].value > 0:
        days_since = len(closes) - 1 - entry
        change_since = closes[-1].value / closes[entry].value - 1
    results = run_study([e.to_event() for e in comparable], closes,
                        horizons=horizons, entry=AFTER_NEWS)
    return EventContext(event, days_since, change_since, results)


ENERGY = re.compile(r'\b(oil|crude|brent|wti|opec\+?|gas|lng|tankers?|refiner(y|ies)|'
                    r'pipelines?|barrels?|energy|fuel|petroleum|krone|nok)\b', re.I)


def relevant(title):
    """A headline about energy or about a monitored region."""
    return bool(ENERGY.search(title) or regions_of(title))


def headlines(articles, limit=8):
    """De-duplicated (title, domain, url, seen) tuples, newest first. Only
    headlines whose own title is about energy or a monitored region; GDELT
    matches article text, so many raw results are off-topic."""
    seen, out = set(), []
    for a in sorted(articles, key=lambda a: a.get('seendate', ''), reverse=True):
        title = (a.get('title') or '').strip()
        if not relevant(title):
            continue
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        out.append((title, a.get('domain', ''), a.get('url', ''), a.get('seendate', '')))
        if len(out) >= limit:
            break
    return out
