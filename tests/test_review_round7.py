"""Regression tests for review round 7 (independent reviewer agent, 2026-11-12)."""

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from scripts import approve_event
from scripts.daily_report import candidate_lines
from scripts.suggest_events import read_candidates, run, write_candidates
from src.huginn_muninn.calibration import bootstrap_diff, walk_forward
from src.huginn_muninn.candidates import is_escalation, seen_day, suggest
from src.huginn_muninn.catalog import first_per_episode, load_catalog
from src.huginn_muninn.prices import load_closes

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
THREE = ('a.com', 'b.com', 'c.com')


def art(title, domain, seen):
    return {'title': title, 'domain': domain, 'seendate': seen, 'url': f'https://{domain}/{title[:5]}'}


class P1EveningNewsIsNextDay(unittest.TestCase):
    def test_cutoff(self):
        self.assertEqual(seen_day({'seendate': '20250612T220000Z'}, None), date(2025, 6, 13))
        # Cutoff moved to 12:00 UTC in round 8 (safe for the USD/NOK fixing too).
        self.assertEqual(seen_day({'seendate': '20250612T115959Z'}, None), date(2025, 6, 12))
        self.assertEqual(seen_day({'seendate': '20250612T120000Z'}, None), date(2025, 6, 13))
        self.assertEqual(seen_day({'seendate': 'garbage'}, date(2000, 1, 1)), date(2000, 1, 1))

    def test_reviewer_example_matches_catalog_date(self):
        # The Israeli strike on Iran, first seen 22:00 UTC on 12 June 2025, must get
        # the catalog's date (13 June), not the day before.
        arts = [art(f'Israel strikes Iran nuclear sites {d}', d, '20250612T220000Z') for d in THREE]
        (c,) = suggest(arts, date(2025, 6, 13), [])
        self.assertEqual(c.date_public, date(2025, 6, 13))
        catalog = {e.event_id: e for e in load_catalog(EVENTS)}
        self.assertEqual(c.date_public, catalog['me-2025-twelve-day-war'].date_public)


class P1NoSilentDropOnIdCollision(unittest.TestCase):
    def test_different_story_same_slot_gets_suffix(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            news, cands = tmp / 'n.json', tmp / 'c.csv'
            day1 = [art(f'Drone attack hits Saudi facility {d}', d, '20261111T020000Z') for d in THREE]
            news.write_text(json.dumps({'fetched_at': '2026-11-11T06:23:00+00:00', 'articles': day1}))
            run(date(2026, 11, 11), news, EVENTS, cands, tmp / 'none')
            rows = read_candidates(cands)
            rows[0]['status'] = 'rejected'
            write_candidates(rows, cands)
            day2 = [art(f'Missile strike on Saudi port {d}', d, '20261111T100000Z') for d in THREE]
            news.write_text(json.dumps({'fetched_at': '2026-11-12T06:23:00+00:00', 'articles': day2}))
            new = run(date(2026, 11, 12), news, EVENTS, cands, tmp / 'none')
            self.assertEqual([c['candidate_id'] for c in new], ['c-20261111-saudi-2'])
            self.assertEqual(run(date(2026, 11, 12), news, EVENTS, cands, tmp / 'none'), [])
            events = tmp / 'e.csv'
            shutil.copyfile(EVENTS, events)
            row = approve_event.approve('c-20261111-saudi-2', events=events, candidates=cands)
            self.assertEqual(row['event_id'], 'me-2026-saudi-1111-2')
        finally:
            shutil.rmtree(tmp)


class P1DailyJobRebuildsOnTopOfMain(unittest.TestCase):
    def test_commit_step_resets_and_rebuilds_instead_of_rebasing(self):
        text = (ROOT / '.github' / 'workflows' / 'fetch-prices.yml').read_text()
        step = text[text.index('Commit prices, news and brief'):]
        self.assertIn('git reset -q --hard origin/main', step)
        self.assertIn('for attempt in 1 2 3', step)
        self.assertIn('cp -r /tmp/fetched/prices /tmp/fetched/news data/', step)
        self.assertNotIn('pull --rebase', step)


class P2SecondStorySameDay(unittest.TestCase):
    # Round 8 decision: the keyword screen gives ONE candidate per region and day
    # (splitting by wording split single events); the AI screen separates events.
    def test_reviewer_example(self):
        arts = ([art(f'Iranian missile attack on Israel {d}', d, '20261111T080000Z') for d in THREE]
                + [art(f'Israel airstrike kills commander in Jenin {d}', d, '20261111T090000Z')
                   for d in ('d.com', 'e.com', 'f.com')])
        found = suggest(arts, date(2026, 11, 11), [])
        self.assertEqual(len(found), 1)
        # The Jenin story is not lost: its articles (d/e/f.com) are on the candidate.
        for site in ('a.com', 'd.com', 'e.com', 'f.com'):
            self.assertIn(site, found[0].urls)


class P2BacktestUncertainty(unittest.TestCase):
    def test_interval_and_wording(self):
        events = [e.to_event() for e in first_per_episode(load_catalog(EVENTS))]
        preds = walk_forward(events, load_closes(ROOT / 'data/prices/brent.csv'), 20)
        d, lo, hi = bootstrap_diff(preds)
        self.assertLess(lo, d)
        self.assertLess(d, hi)
        self.assertEqual(bootstrap_diff(preds), (d, lo, hi))  # seeded, reproducible
        from scripts.backtest import build
        text = build()
        self.assertIn('95% interval', text)
        self.assertIn('12 comparisons', text)
        self.assertIn('picked by hand with hindsight', text)
        self.assertNotIn('under about 0.03 are noise', text)


class P3Vocabulary(unittest.TestCase):
    def test_reviewer_examples(self):
        self.assertTrue(is_escalation('Israel shells southern Lebanon villages'))
        self.assertTrue(is_escalation('Israeli strike hits football stadium in Gaza, killing 12'))
        self.assertTrue(is_escalation('Israel strikes Hezbollah targets as investors flee Lebanese bonds'))
        self.assertTrue(is_escalation('Israel strikes Iran as tanker pay rates surge'))
        self.assertFalse(is_escalation('Iran and Saudi Arabia struck a deal in Beijing'))
        self.assertFalse(is_escalation('Shell profits rise on higher margins'))
        self.assertFalse(is_escalation('Iraqi oil workers strike at Basra fields'))


class P3StrictDate(unittest.TestCase):
    def test_compact_date_rejected(self):
        out = subprocess.run(['python3', 'scripts/approve_event.py', 'c-x', '--date', '20261111'],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn('YYYY-MM-DD', out.stderr)


class P3HintRendering(unittest.TestCase):
    def test_episode_hint_not_mangled(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_candidates([{'candidate_id': 'c-20261112-iran', 'date_public': '2026-11-12',
                               'title': 'T', 'region': 'iran', 'episode_hint': '2026-iran-war',
                               'source_url': 'https://x', 'n_sites': '3', 'status': 'pending',
                               'method': 'ai', 'event_type': 'airstrike'}], tmp / 'c.csv')
            text = '\n'.join(candidate_lines(date(2026, 11, 12), tmp / 'c.csv', tmp / 'none'))
            self.assertIn('may belong to episode 2026-iran-war', text)
            self.assertNotIn("'2026-iran-war'", text)
        finally:
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
