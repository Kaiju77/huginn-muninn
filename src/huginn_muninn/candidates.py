"""Suggest new catalog events from headlines (free, keyword based).

A region becomes a candidate when at least ``min_domains`` different news
sites run an escalation headline about it on the same day. This is a
screening rule, not a judgment: Kai approves or ignores every candidate.
"""

import re
from datetime import date, timedelta
from typing import NamedTuple

ESCALATION = re.compile(
    r'\b(attack(s|ed|ing)?|strik(e|es|ed|ing)|struck|airstrikes?|missiles?|drones?|rockets?|'
    r'invad(e|es|ed|ing)|invasion|seiz(e|es|ed|ing|ure)|hijack(s|ed|ing)?|blockade|'
    r'bomb(s|ed|ing)?|explosions?|shell(ing|ed)|raid(s|ed)?|'
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

# Words that make "strike"/"offensive" mean labour or business, not military.
# Only applied when those two are the sole escalation words in the headline.
AMBIGUOUS = {'strike', 'strikes', 'striking', 'offensive'}
NOT_MILITARY_STRIKE = re.compile(
    r'\b(deals?|agreements?|accords?|workers?|unions?|labou?r|walkouts?|wages?|pay|'
    r'charm|sales|marketing|investors?)\b', re.I)

# Sport only. Generic words (team, league, match, cup, goal) were removed after
# review round 6: "Arab League condemns...", "UN aid team" are real news.
NON_MILITARY = re.compile(
    r'\b(football|soccer|fifa|olympics?|striker|tournament|championship|qualifiers?|'
    r'world cup|premier league|champions league|kick-?off)\b', re.I)


def is_escalation(title):
    words = {m.group(0).lower() for m in ESCALATION.finditer(title)}
    if not words or NON_MILITARY.search(title):
        return False
    if words <= AMBIGUOUS and NOT_MILITARY_STRIKE.search(title):
        return False
    return True


def seen_day(article, fallback):
    """UTC date of a GDELT seendate ('20261111T080000Z'), else ``fallback``."""
    s = (article.get('seendate') or '')[:8]
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return fallback


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
    """Candidates from the day's articles.

    The candidate's date is the UTC day of its earliest report (not the fetch
    day), so the first day's market reaction is not lost. One headline that
    names several regions ("Iranian missile attack on Israel") yields one
    candidate: regions are taken by number of sites, and a region whose
    articles were mostly used already is skipped.
    """
    groups = {}
    for a in articles:
        title = (a.get('title') or '').strip()
        if not title or not is_escalation(title):
            continue
        for region in regions_of(title):
            groups.setdefault(region, []).append(a)
    ranked = sorted(groups.items(),
                    key=lambda kv: (-len({a.get('domain') for a in kv[1]}), kv[0]))
    used, out = set(), []
    for region, items in ranked:
        domains = {a.get('domain', '') for a in items if a.get('domain')}
        if len(domains) < min_domains:
            continue
        ids = {id(a) for a in items}
        if len(ids & used) * 2 >= len(ids):
            continue  # same story as a region already chosen
        used |= ids
        top = sorted(items, key=lambda a: a.get('seendate', ''))[0]  # earliest report
        day = seen_day(top, on)
        recent = [e for e in catalog if 0 <= (day - e.date_public).days <= recent_days
                  and region in regions_of(e.title + ' ' + e.region.replace('/', ' '))]
        hint = max(recent, key=lambda e: e.date_public).episode if recent else ''
        out.append(Candidate(
            f'c-{day.strftime("%Y%m%d")}-{region}', day, top['title'].strip(), region,
            hint, top.get('url', ''), len(domains)))
    return sorted(out, key=lambda c: c.candidate_id)
