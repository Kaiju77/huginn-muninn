"""Regression tests for review round 11 (Fable 5.2, 2026-11-12)."""

import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts.suggest_events import read_candidates, run as suggest_run, write_candidates
from src.huginn_muninn import predictions as pr
from src.huginn_muninn.candidates import is_escalation
from src.huginn_muninn.catalog import CatalogEvent
from src.huginn_muninn.study import Close
from src.huginn_muninn.ucdp_events import GedRow, find_onsets

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def weekdays(start, end):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class F1OilRowsStillLoggedAfterKrone(unittest.TestCase):
    def test_reviewer_scenario(self):
        event = CatalogEvent('me-2026-x-1110', date(2026, 11, 10), 'X', 'mideast-conflict', 'Iran',
                             'ep-x', 'https://x', False, '')
        history = [Close(d, 50 + i * 0.01) for i, d in
                   enumerate(weekdays(date(1990, 1, 1), date(2026, 11, 30)))]
        comparables = []  # few comparables is fine for this test
        nok = [c for c in history]
        log = []
        for today, brent_until in ((date(2026, 11, 10), date(2026, 11, 3)),
                                   (date(2026, 11, 11), date(2026, 11, 3)),
                                   (date(2026, 11, 17), date(2026, 11, 12))):
            recent = pr.first_of_episodes([event], [event], {r.event_id for r in log})
            closes = {'usd_nok': [c for c in nok if c.on <= today],
                      'brent': [c for c in history if c.on <= brent_until]}
            log = pr.record(log, today, recent, lambda e: comparables, closes)
        assets = {r.asset_id for r in log}
        self.assertEqual(assets, {'usd_nok', 'brent'})
        self.assertEqual(len([r for r in log if r.asset_id == 'brent']), 3)

    def test_other_event_of_same_crisis_still_skipped(self):
        a = CatalogEvent('a', date(2026, 11, 10), 'A', 'c', 'Iran', 'ep', 'https://x', False, '')
        b = CatalogEvent('b', date(2026, 11, 12), 'B', 'c', 'Iran', 'ep', 'https://x', False, '')
        self.assertEqual(pr.first_of_episodes([a], [a, b], {'b'}), [])
        self.assertEqual(pr.first_of_episodes([a], [a, b], {'a'}), [a])


def ged(day, best, prec=1, start=None, i=0):
    d = date.fromisoformat(day)
    return GedRow(id=str(i), date_start=date.fromisoformat(start) if start else d, date_end=d,
                  date_prec=prec, country='Iraq', country_id=645, region='Middle East',
                  type_of_violence=1, best=best)


class F2ManySmallFuzzyRowsBlock(unittest.TestCase):
    def test_reviewer_examples(self):
        war = ged('2003-03-20', 3000, i=999)
        many = [ged('2003-02-28', 99, prec=4, start='2003-02-01', i=k) for k in range(10)]
        self.assertEqual(find_onsets(many + [war]), [])
        week = [ged('2003-02-07', 24, prec=4, start='2003-02-01', i=k) for k in range(3)]
        self.assertEqual(find_onsets(week + [war]), [])
        mixed = [ged('2003-02-05', 20, i=50), ged('2003-02-14', 40, prec=4, start='2003-02-01', i=51)]
        self.assertEqual(find_onsets(mixed + [war]), [])
        self.assertEqual(len(find_onsets([ged('2003-12-31', 1, prec=5, start='2003-01-01'), war])), 1)


class F3F4MilitaryHeadlinesPass(unittest.TestCase):
    def test_reviewer_examples(self):
        for title in ('Israeli pilots strike Iranian nuclear site at Natanz',
                      'IDF chief of staff orders strike on Beirut',
                      'Gaza hospital staff say Israeli strike hit ward',
                      'Aid workers say Israeli strike hit Gaza convoy',
                      'Iranian nurses killed in strike on Tehran hospital',
                      'Hezbollah vows revenge on strike that killed commander',
                      'Israel launches national strike plan against Iran',
                      'Israeli strike hits Gaza football pitch',
                      'Rocket strikes Tel Aviv during Champions League match',
                      'Houthi drone attack halts Saudi football championship in Jeddah',
                      'Crude rockets fired from Gaza land in southern Israel',
                      'Saudi-led coalition offensive on markets in Hodeidah kills 10',
                      'Israel struck a defence contract factory in Tehran'):
            self.assertTrue(is_escalation(title), title)

    def test_unmistakable_non_military_still_vetoed(self):
        for title in ('Qatar strikes $20bn LNG supply deal', 'Iran strikes gold at Asian Games',
                      'Oil price rockets as Iran tensions rise', 'Iraqi oil workers strike over pay',
                      'Saudi Aramco launches charm offensive with investors'):
            self.assertFalse(is_escalation(title), title)


class F5F6SameStoryLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.news, self.cands = self.tmp / 'n.json', self.tmp / 'c.csv'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_one_shared_roundup_link_with_short_ai_row(self):
        write_candidates([{'candidate_id': 'c-20261110-iran', 'date_public': '2026-11-10',
                           'title': 'Israel strikes Iranian oil depot', 'region': 'iran',
                           'source_url': 'https://x/1', 'status': 'approved', 'method': 'ai',
                           'urls': 'https://x/1|https://roundup/live'}], self.cands)
        arts = [{'title': f'Iran fires missiles at Gulf tankers {i}', 'domain': f'c{i}',
                 'seendate': '20261111T060000Z', 'url': f'https://c{i}/1'} for i in range(8)]
        arts.append({'title': 'Iran missiles hit tankers', 'domain': 'roundup',
                     'seendate': '20261111T060000Z', 'url': 'https://roundup/live'})
        self.news.write_text(json.dumps({'fetched_at': '2026-11-11T06:23:00+00:00', 'articles': arts}))
        self.assertEqual(len(suggest_run(date(2026, 11, 11), self.news, EVENTS, self.cands,
                                         self.tmp / 'none')), 1)

    def test_rejected_story_with_two_late_articles_not_revived(self):
        def art(i, seen):
            return {'title': f'Israeli strike on Gaza port {i}', 'domain': f's{i}', 'seendate': seen,
                    'url': f'https://s{i}/x'}
        day1 = [art(i, '20261110T100000Z') for i in range(6)] + [art(i, '20261110T200000Z')
                                                                for i in (6, 7)]
        self.news.write_text(json.dumps({'fetched_at': '2026-11-10T21:00:00+00:00', 'articles': day1}))
        suggest_run(date(2026, 11, 10), self.news, EVENTS, self.cands, self.tmp / 'none')
        rows = read_candidates(self.cands)
        rows[0]['status'] = 'rejected'
        write_candidates(rows, self.cands)
        day2 = [art(i, '20261110T200000Z') for i in (6, 7)] + [art(i, '20261111T080000Z')
                                                             for i in range(10, 19)]
        self.news.write_text(json.dumps({'fetched_at': '2026-11-11T21:00:00+00:00', 'articles': day2}))
        self.assertEqual(suggest_run(date(2026, 11, 11), self.news, EVENTS, self.cands,
                                     self.tmp / 'none'), [])


class F7LateBatchLeavesVisibleVoid(unittest.TestCase):
    def test_reviewer_scenario(self):
        event = CatalogEvent('e', date(2026, 11, 4), 'E', 'c', 'Iran', 'ep', 'https://x', False, '')
        closes = [Close(d, 70.0 + i * 0.01) for i, d in
                  enumerate(weekdays(date(1990, 1, 1), date(2026, 11, 11)))]
        rows = pr.record([], date(2026, 11, 18), [event], lambda e: [], {'brent': closes})
        by_h = {r.horizon: r.status for r in rows}
        self.assertEqual(by_h, {5: pr.VOID, 20: pr.OPEN, 60: pr.OPEN})


if __name__ == '__main__':
    unittest.main()
