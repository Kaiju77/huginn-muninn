"""Regression tests for review round 8 (independent reviewer agent, 2026-11-12)."""

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.backtest import build
from scripts.suggest_events import read_candidates, run, write_candidates
from src.huginn_muninn.candidates import is_escalation, seen_day, suggest

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
DAY = date(2026, 11, 12)


def art(title, domain, seen='20261112T080000Z', path='x'):
    return {'title': title, 'domain': domain, 'seendate': seen, 'url': f'https://{domain}/{path}'}


def write_news(path, arts):
    path.write_text(json.dumps({'fetched_at': '2026-11-12T10:47:00+00:00', 'articles': arts}))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.news, self.cands = self.tmp / 'n.json', self.tmp / 'c.csv'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def ids(self):
        return [r['candidate_id'] for r in read_candidates(self.cands)]


class F1UniqueIdsWhenAiReplacesSuffixedReject(Base):
    def test_reviewer_example(self):
        write_candidates([
            {'candidate_id': 'c-20261112-israel', 'date_public': '2026-11-12', 'title': 'A',
             'region': 'israel', 'source_url': 'https://a/1', 'status': 'pending', 'method': 'keyword'},
            {'candidate_id': 'c-20261112-israel-2', 'date_public': '2026-11-12', 'title': 'B',
             'region': 'israel', 'source_url': 'https://b/1', 'status': 'rejected', 'method': 'keyword'},
        ], self.cands)
        write_news(self.news, [art('Israel raid', 'b', path='1')])
        ai = self.tmp / 'ai.json'
        ai.write_text(json.dumps({'date': DAY.isoformat(), 'ok': True, 'rejected': 0, 'candidates': [{
            'candidate_id': 'c-20261112-israel', 'date_public': '2026-11-12', 'title': 'AI title',
            'region': 'israel', 'source_url': 'https://b/1', 'n_sites': 2, 'event_type': 'attack',
            'urls': 'https://b/1'}]}))
        run(DAY, self.news, EVENTS, self.cands, ai)
        ids = self.ids()
        self.assertEqual(len(ids), len(set(ids)))
        replaced = [r for r in read_candidates(self.cands) if r['title'] == 'AI title']
        self.assertEqual(replaced[0]['candidate_id'], 'c-20261112-israel-2')


class F2SameStoryAcrossRuns(Base):
    def morning(self):
        return [art('Israeli strike on Jenin camp', d, '20261112T080000Z', 'j') for d in ('a', 'b', 'c')]

    def test_new_earlier_headline_in_backup_run(self):
        write_news(self.news, self.morning())
        run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none')
        backup = [art('Israeli forces raid Jenin refugee camp', 'z', '20261112T060000Z', 'early')]
        write_news(self.news, backup + self.morning())
        self.assertEqual(run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none'), [])
        self.assertEqual(self.ids(), ['c-20261112-israel'])

    def test_order_flip_does_not_duplicate(self):
        arts = self.morning()
        write_news(self.news, arts)
        run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none')
        write_news(self.news, list(reversed(arts)))
        run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none')
        self.assertEqual(self.ids(), ['c-20261112-israel'])

    def test_ai_retitle_with_other_first_url_is_same_story(self):
        write_news(self.news, self.morning())
        run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none')
        ai = self.tmp / 'ai.json'
        ai.write_text(json.dumps({'date': DAY.isoformat(), 'ok': True, 'rejected': 0, 'candidates': [{
            'candidate_id': 'c-20261112-israel', 'date_public': '2026-11-12',
            'title': 'Israeli airstrike on Jenin refugee camp', 'region': 'israel',
            'source_url': 'https://other/first', 'n_sites': 2, 'event_type': 'airstrike',
            'urls': 'https://b/j|https://other/first'}]}))
        self.assertEqual(run(DAY, self.news, EVENTS, self.cands, ai), [])
        self.assertEqual(self.ids(), ['c-20261112-israel'])

    def test_genuinely_different_story_gets_next_free_suffix(self):
        write_news(self.news, self.morning())
        run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none')
        rows = read_candidates(self.cands)
        rows[0]['status'] = 'rejected'
        write_candidates(rows, self.cands)
        other = [art('Rocket attack on Israeli port of Haifa', d, '20261112T090000Z', 'h') for d in ('d', 'e', 'f')]
        write_news(self.news, other)
        run(DAY, self.news, EVENTS, self.cands, self.tmp / 'none')
        self.assertEqual(self.ids(), ['c-20261112-israel', 'c-20261112-israel-2'])


class F3OneEventTwoWordings(unittest.TestCase):
    def test_reviewer_examples(self):
        arts = ([art('Iran fires ballistic missiles at Israel, sirens across country', d, path='r')
                 for d in ('a', 'b', 'c', 'd')]
                + [art('Iranian missile barrage sends Israelis to shelters', d, path='p')
                   for d in ('e', 'f', 'g', 'h')])
        found = suggest(arts, DAY, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].n_sites, 8)
        arts = ([art('Israeli jets bomb Beirut southern suburbs', d, path='1') for d in ('a', 'b', 'c')]
                + [art('Air raids hit Dahiyeh, Hezbollah stronghold', d, path='2') for d in ('d', 'e', 'f')])
        self.assertEqual(len(suggest(arts, DAY, [])), 1)


class F4DealsAreNotStrikes(unittest.TestCase):
    def test_reviewer_examples(self):
        for title in ('Qatar strikes $20bn LNG supply deal', 'Saudi Arabia strikes $5bn arms deal with US',
                      'UAE strikes multibillion-dollar deal', 'Aramco strikes long-term supply agreement'):
            self.assertFalse(is_escalation(title), title)
        self.assertTrue(is_escalation('Israel strikes Gaza as unions call general strike'))
        self.assertTrue(is_escalation('Israel strikes Iran oil depot'))


class F5CutoffSafeForAllAssets(unittest.TestCase):
    def test_summer_evening_and_nok_fixing(self):
        self.assertEqual(seen_day({'seendate': '20250612T184500Z'}, None), date(2025, 6, 13))
        self.assertEqual(seen_day({'seendate': '20250612T150000Z'}, None), date(2025, 6, 13))
        self.assertEqual(seen_day({'seendate': '20250612T110000Z'}, None), date(2025, 6, 12))


class F6SportVerbs(unittest.TestCase):
    def test_reviewer_examples(self):
        self.assertFalse(is_escalation('Saudi striker rockets Al-Hilal to top of league'))
        self.assertFalse(is_escalation('Qatar World Cup qualifier: Iran drones past UAE'))
        self.assertTrue(is_escalation('Israeli strike hits football stadium in Gaza, killing 12'))


class F7BacktestCountsAreComputed(unittest.TestCase):
    def test_no_hardcoded_counts(self):
        text = build()
        self.assertIn('there are 12 comparisons', text)  # 4 assets x 3 horizons today
        self.assertIn('10 to 13 predictions per row', text)
        src = (ROOT / 'scripts' / 'backtest.py').read_text()
        self.assertNotIn("'12 comparisons", src)


if __name__ == '__main__':
    unittest.main()
