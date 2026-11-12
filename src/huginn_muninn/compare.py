"""Compare two event catalogs: which events agree, and how their base rates
and backtests differ. Pure functions."""

from typing import NamedTuple


class Match(NamedTuple):
    hand_id: str
    hand_date: object
    ucdp_id: str
    ucdp_date: object
    days_apart: int


def match_events(hand, ucdp, max_days=7):
    """Pairs of (hand, ucdp) events within ``max_days`` of each other, nearest
    first, each event used at most once. Returns (matches, hand_only, ucdp_only)."""
    pairs = sorted(((abs((u.date_public - h.date_public).days), h, u)
                    for h in hand for u in ucdp
                    if abs((u.date_public - h.date_public).days) <= max_days),
                   key=lambda p: (p[0], p[1].event_id, p[2].event_id))
    used_h, used_u, matches = set(), set(), []
    for days, h, u in pairs:
        if h.event_id in used_h or u.event_id in used_u:
            continue
        used_h.add(h.event_id)
        used_u.add(u.event_id)
        matches.append(Match(h.event_id, h.date_public, u.event_id, u.date_public, days))
    hand_only = [h for h in hand if h.event_id not in used_h]
    ucdp_only = [u for u in ucdp if u.event_id not in used_u]
    return sorted(matches, key=lambda m: m.hand_date), hand_only, ucdp_only
