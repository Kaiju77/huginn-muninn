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
    r'\b(strik(e|es|ing)|struck)\s+(\S+\s+){0,4}?(deals?|agreements?|accords?|pacts?|'
    r'partnerships?|contracts?|balance|chord)\b|'
    r'\b(workers?|unions?|staff|employees|pilots|dockers|drivers|nurses)\s+(\w+\s+){0,2}'
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
# (Not "rockets"/"drones"/"missiles": sport uses them as verbs, "striker rockets...".)
CASUALTY = re.compile(r'\b(kill(s|ed|ing)?|dead|deaths?|wounded|injur(ed|ies)|'
                      r'airstrikes?|bomb(s|ed|ing)?|casualties)\b', re.I)


def is_escalation(title):
    if not ESCALATION.search(title):
        return False
    if NON_MILITARY.search(title) and not CASUALTY.search(title):
        return False
    # Escalation unless every match is an ambiguous word inside a labour or
    # business phrase ("Israel strikes Gaza as unions call general strike" counts).
    spans = [m.span() for m in NOT_MILITARY_STRIKE.finditer(title)]
    for m in ESCALATION.finditer(title):
        if m.group(0).lower() not in AMBIGUOUS:
            return True
        if not any(a <= m.start() and m.end() <= b for a, b in spans):
            return True
    return False


# News first seen at or after 12:00 UTC is dated the next day, so the after_news
# entry is always a price fixed after the news, for every asset: Norges Bank
# fixes USD/NOK at 14:15 CET (12:15 UTC in summer) and Brent settles around
# 19:30 London (18:30 UTC in summer). Earlier cutoffs (19:00) let some news be
# dated before a close it followed (review rounds 7 and 8). Dating later is
# conservative: it can miss part of a first-day reaction but never peeks ahead.
CLOSE_CUTOFF_UTC_HOUR = 12


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
           'source_url', 'n_sites', 'status', 'method', 'event_type', 'urls')


class Candidate(NamedTuple):
    candidate_id: str
    date_public: date
    title: str
    region: str
    episode_hint: str
    source_url: str
    n_sites: int
    status: str = 'pending'
    urls: str = ''      # every supporting article URL, '|'-separated


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
    # Split each region into stories by shared headline words, so two different
    # Israel stories on one day stay two candidates (review round 7).
    # One candidate per region and day. Splitting a region into stories by
    # wording split single events (wire services word them differently;
    # review round 8); separating events is the AI screen's job.
    ranked = sorted(groups.items(),
                    key=lambda kv: (-len({a.get('domain') for a in kv[1]}), kv[0]))
    used, out = set(), []
    for region, items in ranked:
        # Articles already behind a chosen candidate don't count again, so
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
        out.append(Candidate(
            f'c-{day.strftime("%Y%m%d")}-{region}', day, top['title'].strip(), region,
            hint, top.get('url', ''), len(domains),
            urls='|'.join(sorted({a.get('url', '') for a in fresh if a.get('url')}))))
    return sorted(out, key=lambda c: c.candidate_id)
