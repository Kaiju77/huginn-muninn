"""Regression tests for review round 10 (Fable 5.2, 2026-11-12)."""

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import prediction_log
from scripts.suggest_events import read_candidates, run as suggest_run, write_candidates
from src.huginn_muninn import predictions as pr
from src.huginn_muninn.candidates import is_escalation
from src.huginn_muninn.catalog import load_catalog
from src.huginn_muninn.ucdp_events import GedRow, find_onsets

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def ged(day, best, prec=1, start=None):
    d = date.fromisoformat(day)
    return GedRow(id=str(hash((day, best, prec))), date_start=date.fromisoformat(start) if start else d,
                  date_end=d, date_prec=prec, country='Iraq', country_id=645,
                  region='Middle East', type_of_violence=1, best=best)


class F1SmallFuzzyRowsDoNotBlock(unittest.TestCase):
    def test_reviewer_examples(self):
        war = ged('2003-03-20', 3000)
        self.assertEqual(len(find_onsets([war])), 1)
        self.assertEqual(len(find_onsets([war, ged('2003-12-31', 1, prec=5, start='2003-01-01')])), 1)
        self.assertEqual(len(find_onsets([war, ged('2003-01-31', 1, prec=4, start='2003-01-01')])), 1)

    def test_big_fuzzy_row_still_blocks(self):
        self.assertEqual(find_onsets([ged('2003-01-31', 1000, prec=4, start='2003-01-01'),
                                      ged('2003-03-20', 3000)]), [])


class F10FuzzyRowReachesBackOneWindow(unittest.TestCase):
    def test_reviewer_example(self):
        onset = ged('2000-06-01', 30)
        for end in ('2000-02-28', '2000-03-03'):
            rows = [ged(end, 1000, prec=4, start='2000-02-01'), onset]
            self.assertEqual(find_onsets(rows), [], end)


class F2DifferentStoryAcrossDaysKept(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.news, self.cands = self.tmp / 'n.json', self.tmp / 'c.csv'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def news_on(self, fetched, arts):
        self.news.write_text(json.dumps({'fetched_at': fetched, 'articles': arts}))

    def test_repeated_headline_days_later_with_new_sources(self):
        self.news_on('2026-11-10T06:23:00+00:00', [
            {'title': 'Israel strikes Beirut', 'domain': f'a{i}', 'seendate': '20261110T060000Z',
             'url': f'https://a{i}/1'} for i in range(3)])
        suggest_run(date(2026, 11, 10), self.news, EVENTS, self.cands, self.tmp / 'none')
        rows = read_candidates(self.cands)
        rows[0]['status'] = 'rejected'
        write_candidates(rows, self.cands)
        self.news_on('2026-11-12T06:23:00+00:00', [
            {'title': 'Israel strikes Beirut', 'domain': f'b{i}', 'seendate': '20261112T060000Z',
             'url': f'https://b{i}/1'} for i in range(8)])
        new = suggest_run(date(2026, 11, 12), self.news, EVENTS, self.cands, self.tmp / 'none')
        self.assertEqual(len(new), 1)

    def test_one_shared_roundup_link_is_not_the_same_story(self):
        write_candidates([{'candidate_id': 'c-20261110-iran', 'date_public': '2026-11-10',
                           'title': 'Israel strikes Iranian oil depot', 'region': 'iran',
                           'source_url': 'https://x/1', 'status': 'approved', 'method': 'ai',
                           'urls': 'https://x/1|https://x/2|https://roundup/live'}], self.cands)
        arts = [{'title': f'Iran fires missiles at Gulf tankers {i}', 'domain': f'c{i}',
                 'seendate': '20261111T060000Z', 'url': f'https://c{i}/1'} for i in range(8)]
        arts.append({'title': 'Iran missiles hit tankers', 'domain': 'roundup',
                     'seendate': '20261111T060000Z', 'url': 'https://roundup/live'})
        self.news_on('2026-11-11T06:23:00+00:00', arts)
        new = suggest_run(date(2026, 11, 11), self.news, EVENTS, self.cands, self.tmp / 'none')
        self.assertEqual(len(new), 1)


class F3OpenerApprovedAfterFollowUp(unittest.TestCase):
    def test_episode_logged_once(self):
        catalog = load_catalog(EVENTS)
        follow = [e for e in catalog if e.event_id == 'me-2025-us-strikes-iran']
        opener = [e for e in catalog if e.event_id == 'me-2025-twelve-day-war']
        # The follow-up was logged first (opener not yet in the catalog then).
        self.assertEqual(pr.first_of_episodes(opener + follow, catalog,
                                              {'me-2025-us-strikes-iran'}), [])


class F4EntryAgeCoversEiaLag(unittest.TestCase):
    def test_cap(self):
        self.assertGreaterEqual(pr.MAX_ENTRY_AGE_DAYS, 14)


class F5MilitaryHeadlinesPass(unittest.TestCase):
    def test_reviewer_examples(self):
        for title in ('Israel strikes back at Iran', 'Israel strikes again in Beirut suburbs',
                      'Israel strikes first as Iran readies retaliation',
                      'Houthi missile attack hits Saudi Aramco depot near Jeddah Grand Prix track',
                      'Israeli soldiers awarded medals after Iran strikes'):
            self.assertTrue(is_escalation(title), title)


class F6BackfillLabelledAndNeverLive(unittest.TestCase):
    def test_label_in_file_and_live_report_protected(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            prediction_log.run(date(2025, 6, 16), tmp / 'bf.csv', tmp / 'bf.md',
                               allow_backfill=True, now=date(2026, 11, 12))
            self.assertIn('BACKFILL', (tmp / 'bf.md').read_text())
            with self.assertRaises(prediction_log.BackfillRefused):
                prediction_log.run(date(2025, 6, 16), tmp / 'x.csv', prediction_log.REPORT,
                                   allow_backfill=True, now=date(2026, 11, 12))
        finally:
            shutil.rmtree(tmp)


class F7DealsAndCeasefires(unittest.TestCase):
    def test_reviewer_examples(self):
        for title in ('Israel strikes Gaza, breaking ceasefire deal',
                      'Israel strikes Gaza hours before ceasefire deal takes effect',
                      'Israel strikes Iran, endangering nuclear deal'):
            self.assertTrue(is_escalation(title), title)
        for title in ('Qatar strikes in-principle LNG deal with Shell',
                      'Qatar strikes $20bn LNG supply deal',
                      'Aramco strikes long-term supply agreement'):
            self.assertFalse(is_escalation(title), title)
        # Accepted false alarm under recall-first: a labour strike phrased oddly.
        self.assertTrue(is_escalation('Kuwait strikes over pay deal enter second week'))


class F8OilAsNoun(unittest.TestCase):
    def test_reviewer_example(self):
        self.assertTrue(is_escalation('Iraqi oil rockets: militia fires on Basra field'))
        self.assertFalse(is_escalation('Oil price rockets as Iran tensions rise'))


class F9MalformedDateDoesNotStopCandidates(unittest.TestCase):
    def test_hand_edited_date(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_candidates([{'candidate_id': 'c-x', 'date_public': '10.11.2026', 'title': 'T',
                               'region': 'iran', 'status': 'pending'}], tmp / 'c.csv')
            (tmp / 'n.json').write_text(json.dumps({'fetched_at': '2026-11-12T06:23:00+00:00',
                'articles': [{'title': 'Missile strike on Iranian refinery', 'domain': f'd{i}',
                              'seendate': '20261112T060000Z', 'url': f'https://d{i}/1'}
                             for i in range(3)]}))
            new = suggest_run(date(2026, 11, 12), tmp / 'n.json', EVENTS, tmp / 'c.csv', tmp / 'n')
            self.assertEqual(len(new), 1)
        finally:
            shutil.rmtree(tmp)


class F11ReportWording(unittest.TestCase):
    def test_says_one_crisis_counts_once(self):
        text = (ROOT / 'scripts' / 'prediction_log.py').read_text()
        self.assertIn('so a crisis counts once', text)


if __name__ == '__main__':
    unittest.main()
