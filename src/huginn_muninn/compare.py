"""Compare two event catalogs (hand-picked vs rule-based UCDP). Pure functions.

Matching is done per crisis episode, not per event: a hand episode and a UCDP
episode agree when any event of one is within ``max_days`` of any event of the
other AND their countries overlap. Each episode is used at most once.
"""

from datetime import timedelta
from typing import NamedTuple

# Hand-catalog region words that are not a UCDP country, mapped to the GED
# countries where such an event would be recorded.
WATERS = {
    'gulf of oman': {'Iran', 'Oman', 'United Arab Emirates'},
    'persian gulf': {'Iran', 'Iraq', 'Kuwait', 'Saudi Arabia', 'Bahrain', 'Qatar',
                     'United Arab Emirates'},
    'red sea': {'Yemen', 'Saudi Arabia'},
    'gaza': {'Israel'},      # GED files Gaza and the West Bank under Israel
    'west bank': {'Israel'},
    'palestine': {'Israel'},
}
CHANCE_SHIFTS_DAYS = (-365, -300, -240, -180, -120, -60, 60, 120, 180, 240, 300, 365)


def countries_of(region):
    out = set()
    for part in str(region).split('/'):
        p = part.strip()
        out |= WATERS.get(p.lower(), {p} if p else set())
    return out


class Episode(NamedTuple):
    episode: str
    opener: object          # first CatalogEvent of the episode
    events: tuple

    @property
    def start(self):
        return self.opener.date_public

    @property
    def countries(self):
        out = set()
        for e in self.events:
            out |= countries_of(e.region)
        return out


def episodes(events):
    groups = {}
    for e in sorted(events, key=lambda e: (e.date_public, e.event_id)):
        groups.setdefault(e.episode, []).append(e)
    return [Episode(k, v[0], tuple(v)) for k, v in groups.items()]


class Match(NamedTuple):
    hand: Episode
    ucdp: Episode
    hand_event: object
    ucdp_event: object
    days_apart: int


def _closest(h, u, max_days, shift):
    if not (h.countries & u.countries):
        return None
    best = None
    for a in h.events:
        for b in u.events:
            d = abs((b.date_public + timedelta(days=shift) - a.date_public).days)
            if d <= max_days and (best is None or d < best[0]):
                best = (d, a, b)
    return best


def match_episodes(hand, ucdp, max_days=7, shift=0):
    """(matches, hand_only, ucdp_only) over lists of Episode.

    Maximum one-to-one matching (augmenting paths), so one close pair can never
    block two agreements; each episode tries its nearest partner first.
    ``shift`` moves every UCDP date (used by the chance test)."""
    edges = {}
    for i, h in enumerate(hand):
        opts = []
        for j, u in enumerate(ucdp):
            c = _closest(h, u, max_days, shift)
            if c:
                opts.append((c[0], u.start, u.episode, j, c))
        edges[i] = sorted(opts)
    owner = {}          # ucdp index -> hand index

    def augment(i, seen):
        for _, _, _, j, _ in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or augment(owner[j], seen):
                owner[j] = i
                return True
        return False

    for i in sorted(edges, key=lambda i: (hand[i].start, hand[i].episode)):
        augment(i, set())
    matches = []
    for j, i in owner.items():
        d, a, b = next(c for _, _, _, jj, c in edges[i] if jj == j)
        matches.append(Match(hand[i], ucdp[j], a, b, d))
    used_h = {m.hand.episode for m in matches}
    used_u = {m.ucdp.episode for m in matches}
    return (sorted(matches, key=lambda m: m.hand.start),
            [h for h in hand if h.episode not in used_h],
            [u for u in ucdp if u.episode not in used_u])


def chance_matches(hand, ucdp, max_days=7, shifts=CHANCE_SHIFTS_DAYS):
    """Average number of matches when the UCDP dates are moved by months:
    how many 'agreements' the date and country rule produces by luck."""
    counts = [len(match_episodes(hand, ucdp, max_days, s)[0]) for s in shifts]
    return sum(counts) / len(counts)


def in_window(eps, start, end):
    inside = [e for e in eps if start <= e.start <= end]
    outside = [e for e in eps if not (start <= e.start <= end)]
    return inside, outside


def coverage_window(rule, ged_end):
    """First and last public dates at which the UCDP rule could produce an onset."""
    first = rule.data_start + timedelta(days=rule.calm_days + rule.window_days - 1 + rule.lag_days)
    return first, ged_end + timedelta(days=rule.lag_days)
