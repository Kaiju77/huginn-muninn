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
    r'bomb(s|ed|ing)?|explosions?|shells|shell(ing|ed)|raid(s|ed)?|'
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
AMBIGUOUS = {'strike', 'strikes', 'striking', 'struck', 'offensive'}
# Phrases where those words are labour or business, matched near the word itself,
# so "Israel strikes Hezbollah targets as investors flee" still counts.
NOT_MILITARY_STRIKE = re.compile(
    r'\b(strik(e|es|ing)|struck)\s+(a\s+|an\s+|new\s+)?(deals?|agreements?|accords?|'
    r'pacts?|partnerships?|balance|chord|gold|oil\b(?!\s+(facilit|terminal|field|tanker)))|'
    r'\b(workers?|unions?|staff|employees|pilots|dockers|drivers|nurses)\s+(\w+\s+)?'
    r'(strike|strikes|striking|walk\s*out)|'
    r'\b(on|general|labou?r|national)\s+strike\b|\bstrike\s+(action|ballot|pay)\b|'
    r'\bcharm\s+offensive\b|\boffensive\s+(on|in)\s+(sales|pricing|markets?)\b', re.I)

# Sport only. Generic words (team, league, match, cup, goal) were removed after
# review round 6: "Arab League condemns...", "UN aid team" are real news.
NON_MILITARY = re.compile(
    r'\b(football|soccer|fifa|olympics?|striker|tournament|championship|qualifiers?|'
    r'world cup|premier league|champions league|kick-?off)\b', re.I)
# Words that make a headline military even if it mentions sport
# ("Israeli strike hits football stadium in Gaza, killing 12").
CASUALTY = re.compile(r'\b(kill(s|ed|ing)?|dead|deaths?|wounded|injur(ed|ies)|'
                      r'missiles?|airstrikes?|drones?|rockets?|bomb(s|ed|ing)?)\b', re.I)


def is_escalation(title):
    words = {m.group(0).lower() for m in ESCALATION.finditer(title)}
    if not words:
        return False
    if NON_MILITARY.search(title) and not CASUALTY.search(title):
        return False
    if words <= AMBIGUOUS and NOT_MILITARY_STRIKE.search(title):
        return False
    return True


# Brent settles around 19:30 London time. News first seen at or after 19:00 UTC
# is dated the next day, so the after_news entry is a close printed after the
# news (no look-ahead). Review round 7: dating 22:00 UTC news to the same day
# booked the whole reaction as an "after news" move.
CLOSE_CUTOFF_UTC_HOUR = 19


def seen_day(article, fallback):
    """Public date of a GDELT report: its UTC day, or the next day if it was
    first seen at or after the cutoff. ``fallback`` if seendate is unusable."""
    s = article.get('seendate') or ''
    try:
        day = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        hour = int(s[9:11])
    except ValueError:
        return fallback
    return day + timedelta(days=1) if hour >= CLOSE_CUTOFF_UTC_HOUR else day


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


STOP = {'the', 'a', 'an', 'in', 'on', 'of', 'to', 'for', 'and', 'as', 'at', 'by', 'with',
        'after', 'over', 'from', 'is', 'are', 'says', 'say', 'said', 'new', 'amid'}


def _words(title):
    return {w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 2 and w not in STOP}


def stories(items, threshold=0.25):
    """Group articles whose headlines share enough words (Jaccard >= threshold
    with any member of a group). Simple single-link clustering."""
    groups = []
    for a in items:
        wa = _words(a.get('title', ''))
        hits = [g for g in groups if any(
            len(wa & w) / max(1, len(wa | w)) >= threshold for w in g['words'])]
        if not hits:
            groups.append({'items': [a], 'words': [wa]})
            continue
        first = hits[0]
        first['items'].append(a)
        first['words'].append(wa)
        for g in hits[1:]:  # merge groups this headline links together
            first['items'] += g['items']
            first['words'] += g['words']
            groups.remove(g)
    return [g['items'] for g in groups]


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
    # Split each region into stories by shared headline words, so two different
    # Israel stories on one day stay two candidates (review round 7).
    # Split only when every part is strong enough on its own; one event is
    # usually worded very differently by different sites, and the AI screen
    # separates events properly.
    clusters = []
    for region, items in groups.items():
        parts = stories(items)
        strong = [s for s in parts
                  if len({a.get('domain') for a in s if a.get('domain')}) >= min_domains]
        if len(parts) > 1 and len(strong) == len(parts):
            clusters += [(region, s) for s in parts]
        else:
            clusters.append((region, items))
    clusters.sort(key=lambda rc: (-len({a.get('domain') for a in rc[1]}), rc[0]))
    used, out, slots = set(), [], {}
    for region, items in clusters:
        # Only articles not already behind a chosen candidate count, so
        # "Iranian missile attack on Israel" gives one candidate, not two.
        fresh = [a for a in items if id(a) not in used]
        domains = {a.get('domain', '') for a in fresh if a.get('domain')}
        if len(domains) < min_domains:
            continue
        used |= {id(a) for a in fresh}
        top = sorted(fresh, key=lambda a: a.get('seendate', ''))[0]  # earliest report
        day = seen_day(top, on)
        recent = [e for e in catalog if 0 <= (day - e.date_public).days <= recent_days
                  and region in regions_of(e.title + ' ' + e.region.replace('/', ' '))]
        hint = max(recent, key=lambda e: e.date_public).episode if recent else ''
        base = f'c-{day.strftime("%Y%m%d")}-{region}'
        slots[base] = slots.get(base, 0) + 1
        cid = base if slots[base] == 1 else f'{base}-{slots[base]}'
        out.append(Candidate(cid, day, top['title'].strip(), region, hint,
                             top.get('url', ''), len(domains)))
    return sorted(out, key=lambda c: c.candidate_id)
