"""Suggest new catalog events from headlines (free, keyword based).

A region becomes a candidate when at least ``min_domains`` different news
sites run an escalation headline about it on the same day. This is a
screening rule, not a judgment: Kai approves or ignores every candidate.
"""

import re
from datetime import date, timedelta
from typing import NamedTuple

ESCALATION = re.compile(
    r'\b(attack(s|ed|ing)?|strik(e|es|ed|ing)|airstrikes?|missiles?|drones?|rockets?|'
    r'invad(e|es|ed|ing)|invasion|seiz(e|es|ed|ing|ure)|hijack(s|ed|ing)?|blockade|'
    r'bomb(s|ed|ing)?|explosions?|'
    r'assassinat(e|ed|ion)|offensive|shot down)\b', re.I)
# Not included: "war" (names an ongoing situation, e.g. analysis of "the Iran war",
# not something new today) and "mine(s)" (also mining news). Found 2026-11-12:
# both of that day's keyword candidates were analysis pieces about "the Iran war".

# Region label -> words that place a headline there.
REGIONS = {
    'iran': ('iran', 'iranian', 'tehran', 'irgc'),
    'israel': ('israel', 'israeli', 'idf', 'tel aviv'),
    'gaza': ('gaza', 'hamas'),
    'lebanon': ('lebanon', 'hezbollah', 'beirut'),
    'syria': ('syria', 'syrian', 'damascus'),
    'iraq': ('iraq', 'iraqi', 'baghdad', 'kurdistan'),
    'saudi': ('saudi', 'aramco', 'riyadh'),
    'yemen-red-sea': ('yemen', 'yemeni', 'houthi', 'houthis', 'red sea', 'bab el-mandeb', 'aden'),
    'hormuz-gulf': ('hormuz', 'gulf of oman', 'persian gulf', 'fujairah'),
    'qatar-uae-kuwait': ('qatar', 'uae', 'emirates', 'abu dhabi', 'kuwait'),
    'libya': ('libya', 'libyan', 'tripoli', 'benghazi'),
}

# Headlines about sport use war words ("offensive", "strike", "attack").
NON_MILITARY = re.compile(
    r'\b(football|soccer|match|cup|league|team|tournament|olympics?|fifa|striker|'
    r'goal|coach|championship|qualifier)\b', re.I)


def is_escalation(title):
    return bool(ESCALATION.search(title)) and not NON_MILITARY.search(title)


COLUMNS = ('candidate_id', 'date_public', 'title', 'region', 'episode_hint',
           'source_url', 'n_sites', 'status', 'method', 'event_type')


class Candidate(NamedTuple):
    candidate_id: str
    date_public: date
    title: str
    region: str
    episode_hint: str
    source_url: str
    n_sites: int
    status: str = 'pending'


def regions_of(title):
    low = title.lower()
    return [r for r, words in REGIONS.items()
            if any(re.search(r'\b' + re.escape(w) + r'\b', low) for w in words)]


def suggest(articles, on, catalog, min_domains=3, recent_days=60):
    """Candidates for ``on`` from the day's articles.

    ``episode_hint`` names a catalog episode from the last ``recent_days``
    whose title mentions the same region, so a follow-up event can join it.
    """
    groups = {}
    for a in articles:
        title = (a.get('title') or '').strip()
        if not title or not is_escalation(title):
            continue
        for region in regions_of(title):
            groups.setdefault(region, []).append(a)
    out = []
    for region, items in sorted(groups.items()):
        domains = {a.get('domain', '') for a in items if a.get('domain')}
        if len(domains) < min_domains:
            continue
        top = sorted(items, key=lambda a: a.get('seendate', ''))[0]  # earliest report
        recent = [e for e in catalog if 0 <= (on - e.date_public).days <= recent_days
                  and region in regions_of(e.title + ' ' + e.region.replace('/', ' '))]
        hint = max(recent, key=lambda e: e.date_public).episode if recent else ''
        out.append(Candidate(
            f'c-{on.strftime("%Y%m%d")}-{region}', on, top['title'].strip(), region,
            hint, top.get('url', ''), len(domains)))
    return out
