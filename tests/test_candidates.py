import csv
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts.approve_event import approve
from scripts.daily_report import build
from scripts.suggest_events import read_candidates, run
from src.huginn_muninn.candidates import regions_of, suggest
from src.huginn_muninn.catalog import load_catalog

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def art(title, domain, seen='20261111T080000Z', url=None):
    return {'title': title, 'domain': domain, 'seendate': seen,
            'url': url or f'https://{domain}/a'}


ESCALATION_DAY = [
    art('Missile strike hits Iranian oil terminal', 'a.com', '20261111T070000Z', 'https://a.com/first'),
    art('Iran says drones attacked Kharg Island', 'b.com'),
    art('Explosions reported near Tehran refinery', 'c.com'),
    art('Iran oil exports steady, ministry says', 'd.com'),           # no escalation word
    art('Houthis attack tanker in Red Sea', 'e.com'),                 # only one site
]


class SuggestTest(unittest.TestCase):
    def test_regions(self):
        self.assertEqual(regions_of('Houthis attack ship in Red Sea'), ['yemen-red-sea'])
        self.assertIn('iran', regions_of('Iranian drones'))
        self.assertEqual(regions_of('Irani-born chef wins prize'), [])  # whole words only

    def test_needs_three_sites_and_escalation(self):
        found = suggest(ESCALATION_DAY, date(2026, 11, 11), load_catalog(EVENTS))
        self.assertEqual([c.region for c in found], ['iran'])
        c = found[0]
        self.assertEqual(c.n_sites, 3)
        self.assertEqual(c.source_url, 'https://a.com/first')  # earliest report
        self.assertEqual(c.candidate_id, 'c-20261111-iran')

    def test_analysis_of_an_ongoing_war_is_not_a_new_event(self):
        arts = [art('The Iran War is transforming LNG deals', 'a.com'),
                art('Is more oil going through Hormuz than before the Iran war? No.', 'b.com'),
                art('How the Iran war changed tanker insurance', 'c.com'),
                art('Iran war: what it means for oil', 'd.com')]
        self.assertEqual(suggest(arts, date(2026, 11, 12), []), [])

    def test_same_site_three_times_is_not_enough(self):
        arts = [art(f'Missile strike on Iran {i}', 'same.com') for i in range(5)]
        self.assertEqual(suggest(arts, date(2026, 11, 11), []), [])

    def test_episode_hint_links_to_recent_catalog_episode(self):
        march = [dict(a, seendate='20260310T080000Z') for a in ESCALATION_DAY]
        found = suggest(march, date(2026, 3, 10), load_catalog(EVENTS))
        self.assertEqual(found[0].episode_hint, '2026-iran-war')
        later = suggest(ESCALATION_DAY, date(2026, 11, 11), load_catalog(EVENTS))
        self.assertEqual(later[0].episode_hint, '')


class FlowTest(unittest.TestCase):
    """suggest -> brief shows it -> approve -> catalog has it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.events = self.dir / 'mideast-conflict.csv'
        shutil.copyfile(EVENTS, self.events)
        self.cands = self.dir / 'candidates.csv'
        self.news = self.dir / 'news.json'
        self.news.write_text(json.dumps({'fetched_at': '2026-11-11T12:00:00+00:00',
                                         'articles': ESCALATION_DAY}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_flow(self):
        new = run(date(2026, 11, 11), self.news, self.events, self.cands)
        self.assertEqual(len(new), 1)
        self.assertEqual(run(date(2026, 11, 11), self.news, self.events, self.cands), [])  # no dupes
        self.assertEqual(run(date(2026, 11, 12), self.news, self.events, self.cands), [])  # stale news

        brief = build(date(2026, 11, 11), ROOT / 'data' / 'prices', self.events, self.news,
                      candidates_path=self.cands)
        self.assertIn('Possible new events', brief)
        self.assertIn('`c-20261111-iran`', brief)

        before = len(load_catalog(self.events))
        row = approve('c-20261111-iran', events=self.events, candidates=self.cands)
        catalog = load_catalog(self.events)
        self.assertEqual(len(catalog), before + 1)
        self.assertEqual(row['event_id'], 'me-2026-iran-1111')
        self.assertEqual(row['source_checked'], 'no')
        self.assertEqual(read_candidates(self.cands)[0]['status'], 'approved')
        with self.assertRaises(ValueError):
            approve('c-20261111-iran', events=self.events, candidates=self.cands)
        with self.assertRaises(ValueError):
            approve('c-nope', events=self.events, candidates=self.cands)

        brief = build(date(2026, 11, 11), ROOT / 'data' / 'prices', self.events, self.news,
                      candidates_path=self.cands)
        self.assertNotIn('Possible new events', brief)  # approved, no longer pending
        self.assertIn('Missile strike hits Iranian oil terminal (2026-11-11)', brief)

    def test_approve_with_better_title_and_episode(self):
        run(date(2026, 11, 11), self.news, self.events, self.cands)
        row = approve('c-20261111-iran', 'Strikes on Iranian oil sites', '2026-iran-war',
                      events=self.events, candidates=self.cands)
        self.assertEqual(row['title'], 'Strikes on Iranian oil sites')
        self.assertEqual(row['episode'], '2026-iran-war')

    def test_bad_candidate_never_corrupts_catalog(self):
        run(date(2026, 11, 11), self.news, self.events, self.cands)
        rows = read_candidates(self.cands)
        rows[0]['source_url'] = 'http://not-https'
        with self.cands.open('w', newline='', encoding='utf-8') as h:
            w = csv.DictWriter(h, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        original = self.events.read_bytes()
        with self.assertRaises(ValueError):
            approve('c-20261111-iran', events=self.events, candidates=self.cands)
        self.assertEqual(self.events.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
