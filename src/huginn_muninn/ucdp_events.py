"""Turn UCDP GED event rows into rule-based conflict "onset" events.

Pure functions only: no network, no file writes. The fetcher is
``scripts/fetch_ucdp.py`` and the CLI is ``scripts/build_ucdp_catalog.py``.

Why a rule
----------
The hand-picked catalog (``data/events/mideast-conflict.csv``) is biased:
crises become famous partly because oil moved. A fixed rule applied to every
country-day in UCDP GED picks events without looking at prices.

The rule (all parameters in ``OnsetRule``)
------------------------------------------
For each country separately, take GED rows of the chosen violence types and
add their ``best`` fatality estimate to the day they are anchored to. Let
S(D) be the sum over the ``window_days`` days ending on day D (inclusive).

Day D is an **onset** when

1. S(D) >= ``threshold``, and
2. S(d) < ``threshold`` for every day d in the ``calm_days`` days before D
   (D - calm_days .. D - 1), and
3. that whole calm period lies on or after ``data_start`` (the first day of
   GED coverage). An onset whose calm period was not observed is dropped
   rather than guessed.

One event per onset. A country that stays "hot" produces no new events
until it has been calm for ``calm_days`` days.

Defaults and why
----------------
- ``window_days=7``: a week is long enough to absorb day-to-day noise in
  GED dating and short enough to mark a sharp escalation, not a slow grind.
- ``threshold=25``: 25 battle-related deaths is UCDP's own cut-off for an
  active conflict-year. Here it is applied to one week, so it marks a burst
  of violence that is large by UCDP standards.
- ``calm_days=90``: about a quarter of quiet before an onset counts as new.
  It makes onsets far apart in time, so each one is closer to independent.
- ``types=(1, 2, 3)``: state-based, non-state and one-sided violence all
  count. Narrow to ``(1,)`` for state-based conflict only.
- ``max_date_prec=3``: GED ``date_prec`` 1 = exact day, 2 = 2-6 day range,
  3 = week known, 4 = month, 5 = longer. Rows less precise than a week are
  dropped because they cannot be placed inside a 7-day window.
- ``anchor='date_end'``: for an exact-day row (date_prec 1, most GED rows)
  ``date_start == date_end``. For a row with a date range, ``date_end`` is
  the last day on which the event can have happened, so anchoring there
  never dates an onset before the violence could have been known. Set
  ``anchor='date_start'`` to follow GED's earliest-possible date instead.
- ``lag_days=1``: ``date_public`` = onset date + 1 day. GED dates are when
  violence happened, not when markets learned the death toll; reports and
  casualty counts lag, and fighting late in the day lands after the Brent
  close. One day is a conservative minimum (method rule 1, no look-ahead).
- ``merge_days=30``: onsets in different countries within 30 days of the
  previous onset in the same chain share one ``episode`` (for example
  Israel and Lebanon in July 2006). The study keeps one event per episode,
  so a regional war does not count as several independent events.

Known limits
------------
- GED fatality estimates are retrospective and revised. The rule only uses
  rows dated on or before the onset day, but the counts themselves were
  compiled later. That is a small look-ahead in *selection*, not in prices.
- Final GED (e.g. 26.1) ends on 31 Dec of the previous year. Recent onsets
  need the GED Candidate data, which is not fetched yet.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import NamedTuple

from src.huginn_muninn.catalog import COLUMNS

CATEGORY = 'mideast-conflict-ucdp'
GED_START = date(1989, 1, 1)

# Gleditsch-Ward codes (GED ``country_id``) -> (display name, id slug).
# Palestine has no Gleditsch-Ward code; GED is expected to file events in
# Gaza and the West Bank under Israel (666). UNCONFIRMED: check the
# ``country`` values in a real download.
COUNTRIES = {
    630: ('Iran', 'iran'),
    645: ('Iraq', 'iraq'),
    666: ('Israel', 'israel'),
    660: ('Lebanon', 'lebanon'),
    652: ('Syria', 'syria'),
    678: ('Yemen', 'yemen'),
    680: ('South Yemen', 'south-yemen'),
    670: ('Saudi Arabia', 'saudi-arabia'),
    690: ('Kuwait', 'kuwait'),
    696: ('United Arab Emirates', 'uae'),
    694: ('Qatar', 'qatar'),
    692: ('Bahrain', 'bahrain'),
    698: ('Oman', 'oman'),
    620: ('Libya', 'libya'),
    663: ('Jordan', 'jordan'),
}

SOURCE_URL = 'https://ucdp.uu.se/country/{country_id}'


class GedRow(NamedTuple):
    """The GED columns this project keeps (see scripts/fetch_ucdp.py)."""
    id: str
    date_start: date
    date_end: date
    date_prec: int
    country: str
    country_id: int
    region: str
    type_of_violence: int
    best: int


class OnsetRule(NamedTuple):
    window_days: int = 7
    threshold: int = 25
    calm_days: int = 90
    types: tuple = (1, 2, 3)
    max_date_prec: int = 3
    anchor: str = 'date_end'
    lag_days: int = 1
    merge_days: int = 30
    data_start: date = GED_START

    def check(self):
        if self.window_days < 1:
            raise ValueError('window_days must be at least 1')
        if self.threshold < 1:
            raise ValueError('threshold must be at least 1')
        if self.calm_days < 1:
            raise ValueError('calm_days must be at least 1')
        if not self.types or any(t not in (1, 2, 3) for t in self.types):
            raise ValueError('types must be a non-empty subset of 1, 2, 3')
        if not 1 <= self.max_date_prec <= 5:
            raise ValueError('max_date_prec must be 1-5')
        if self.anchor not in ('date_start', 'date_end'):
            raise ValueError('anchor must be date_start or date_end')
        if self.lag_days < 0:
            raise ValueError('lag_days must not be negative')
        if self.merge_days < 0:
            raise ValueError('merge_days must not be negative')

    def describe(self):
        return (f'rule: >={self.threshold} best-estimate deaths in {self.window_days}d '
                f'after {self.calm_days}d below; types={",".join(map(str, self.types))}; '
                f'date_prec<={self.max_date_prec}; anchor={self.anchor}; '
                f'lag={self.lag_days}d')


class Onset(NamedTuple):
    country_id: int
    country: str
    day: date          # first day the window sum reached the threshold
    window_deaths: int  # S(day)


def country_slug(country_id, name):
    if country_id in COUNTRIES:
        return COUNTRIES[country_id][1]
    slug = ''.join(c if c.isalnum() else '-' for c in name.lower())
    return '-'.join(part for part in slug.split('-') if part) or str(country_id)


def daily_deaths(rows, rule):
    """{country_id: {day: deaths}} after the type and precision filters."""
    out = defaultdict(lambda: defaultdict(int))
    names = {}
    for row in rows:
        if row.type_of_violence not in rule.types or row.date_prec > rule.max_date_prec:
            continue
        day = row.date_end if rule.anchor == 'date_end' else row.date_start
        out[row.country_id][day] += row.best
        names.setdefault(row.country_id, row.country)
    return out, names


def find_onsets(rows, rule=OnsetRule()):
    """Apply the onset rule. Returns Onsets sorted by (day, country_id)."""
    rule.check()
    per_country, names = daily_deaths(rows, rule)
    # Rows too imprecise to date (date_prec > max) still say the period was not
    # calm: an onset whose calm period overlaps one with deaths is not declared
    # (review round 9: a 1000-death January row was dropped, and February was
    # then reported as "after 90 calm days").
    fuzzy = defaultdict(list)
    for row in rows:
        if (row.type_of_violence in rule.types and row.date_prec > rule.max_date_prec
                and row.best > 0):
            fuzzy[row.country_id].append((row.date_start, row.date_end))
    onsets = []
    for country_id, days in per_country.items():
        if not days:
            continue
        first, last = min(days), max(days)
        window = rule.window_days
        running, last_hot = 0, None
        day = first
        while day <= last:
            running += days.get(day, 0)
            running -= days.get(day - timedelta(days=window), 0)
            if running >= rule.threshold:
                calm_ok = last_hot is None or (day - last_hot).days > rule.calm_days
                calm_start = day - timedelta(days=rule.calm_days)
                # The calm check needs every window sum in the calm period, and
                # the first of those reaches window-1 days further back.
                observed = (calm_start - timedelta(days=window - 1)) >= rule.data_start
                unclear = any(s <= day - timedelta(days=1) and e >= calm_start
                              for s, e in fuzzy.get(country_id, ()))
                if calm_ok and observed and not unclear:
                    onsets.append(Onset(country_id, names[country_id], day, running))
                last_hot = day
            day += timedelta(days=1)
    return sorted(onsets, key=lambda o: (o.day, o.country_id))


def to_catalog_rows(onsets, rule=OnsetRule(), today=None, version=''):
    """Catalog rows (dicts with exactly catalog.COLUMNS) for the onsets.
    Onsets whose date_public would be after ``today`` are left out."""
    rule.check()
    today = today or date.today()
    rows, chain_end, episode = [], None, None
    for onset in sorted(onsets, key=lambda o: (o.day, o.country_id)):
        public = onset.day + timedelta(days=rule.lag_days)
        if public > today:
            continue
        slug = country_slug(onset.country_id, onset.country)
        event_id = f'ucdp-{onset.day.year}-{slug}-{onset.day:%m%d}'
        if chain_end is None or (onset.day - chain_end).days > rule.merge_days:
            episode = f'ucdp-{onset.day.isoformat()}-{slug}'
        chain_end = onset.day
        name = COUNTRIES.get(onset.country_id, (onset.country, ''))[0]
        notes = (f'{onset.window_deaths} deaths (UCDP best) in {rule.window_days}d to '
                 f'{onset.day.isoformat()}; {rule.describe()}'
                 + (f'; GED {version}' if version else ''))
        rows.append({
            'event_id': event_id,
            'date_public': public.isoformat(),
            'title': f'UCDP onset in {name}: {onset.window_deaths} deaths in '
                     f'{rule.window_days} days',
            'category': CATEGORY,
            'region': name,
            'episode': episode,
            'source_url': SOURCE_URL.format(country_id=onset.country_id),
            'source_checked': 'no',   # generated by rule, not checked by a person
            'notes': notes,
        })
    assert all(tuple(r) == COLUMNS for r in rows)
    return rows
