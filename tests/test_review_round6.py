"""Regression tests for review round 6 (independent reviewer agent, 2026-11-12)."""

import csv
import json
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from scripts import approve_event
from scripts.daily_report import candidate_lines
from scripts.suggest_events import read_candidates, run, write_candidates
from src.huginn_muninn.ai_screen import numbered, parse
from src.huginn_muninn.candidates import is_escalation, suggest
from src.huginn_muninn.daily import in_window

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
FETCHED = datetime(2026, 11, 12, 6, 23, tzinfo=timezone.utc)


def art(title, domain, seen='20261111T070000Z'):
    return {'title': title, 'domain': domain, 'seendate': seen, 'url': f'https://{domain}/x'}


THREE = ('a.com', 'b.com', 'c.com')


class P1DateIsEarliestReport(unittest.TestCase):
    def test_keyword_candidate_dated_by_seendate(self):
        arts = [art('Missile strike hits Iranian oil terminal', d) for d in THREE]
        (c,) = suggest(in_window(arts, FETCHED), FETCHED.date(), [])
        self.assertEqual((c.candidate_id, c.date_public), ('c-20261111-iran', date(2026, 11, 11)))

    def test_ai_candidate_dated_by_seendate(self):
        arts = [art(f'Missile strike hits Iranian oil terminal ({d})', d) for d in THREE]
        items = numbered(arts, FETCHED)
        cands, _, _ = parse(json.dumps({'events': [{
            'title': 'Strike on Iranian terminal', 'region': 'iran', 'event_type': 'airstrike',
            'headlines': [1, 2, 3], 'happened_today': True, 'relevance': 'high'}]}),
            items, FETCHED.date(), [])
        self.assertEqual(cands[0][0].date_public, date(2026, 11, 11))

    def test_approval_date_can_be_corrected(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            events = tmp / 'e.csv'
            shutil.copyfile(EVENTS, events)
            news = tmp / 'n.json'
            news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': [
                art('Missile strike hits Iranian oil terminal', d) for d in THREE]}))
            run(FETCHED.date(), news, events, tmp / 'c.csv', tmp / 'none.json')
            row = approve_event.approve('c-20261111-iran', events=events,
                                        candidates=tmp / 'c.csv', day='2026-11-10')
            self.assertEqual(row['date_public'], '2026-11-10')
        finally:
            shutil.rmtree(tmp)

    def test_brief_lists_candidate_reported_yesterday(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_candidates([{'candidate_id': 'c-20261111-iran', 'date_public': '2026-11-11',
                               'title': 'T', 'region': 'iran', 'episode_hint': '',
                               'source_url': 'https://x', 'n_sites': '3', 'status': 'pending',
                               'method': 'keyword', 'event_type': ''}], tmp / 'c.csv')
            text = '\n'.join(candidate_lines(date(2026, 11, 12), tmp / 'c.csv', tmp / 'none'))
            self.assertIn('c-20261111-iran', text)
        finally:
            shutil.rmtree(tmp)


class P1WeekendIsScreened(unittest.TestCase):
    def test_workflow_runs_every_day(self):
        text = (ROOT / '.github' / 'workflows' / 'fetch-prices.yml').read_text()
        self.assertIn("cron: '23 6 * * *'", text)
        self.assertNotIn('* * 1-5', text)


class P2SportFilterTooBroad(unittest.TestCase):
    def test_real_news_with_team_or_league_counts(self):
        for title in ('Arab League condemns Israeli airstrike on Gaza hospital',
                      'Israeli strike kills UN aid team in Gaza',
                      'IAEA team says Iran site hit by drone'):
            self.assertTrue(is_escalation(title), title)
        self.assertFalse(is_escalation('Iran football team launches offensive against Qatar'))

    def test_one_sport_like_headline_does_not_sink_ai_event(self):
        arts = [art('Arab League condemns Israeli airstrike on Beirut', 'a.com'),
                art('Israeli airstrike hits Beirut suburb', 'b.com'),
                art('Beirut hit by Israeli airstrike', 'c.com')]
        items = numbered(arts, FETCHED)
        cands, _, rejected = parse(json.dumps({'events': [{
            'title': 'Israeli airstrike on Beirut', 'region': 'lebanon', 'event_type': 'airstrike',
            'headlines': [1, 2, 3], 'happened_today': True, 'relevance': 'high'}]}),
            items, FETCHED.date(), [])
        self.assertEqual((len(cands), rejected), (1, 0))


class P2KeywordVocabulary(unittest.TestCase):
    def test_misses_and_false_alarms(self):
        self.assertTrue(is_escalation('Israeli jets struck targets in southern Lebanon'))
        self.assertTrue(is_escalation('Shelling continues near Gaza border'))
        self.assertTrue(is_escalation('Israeli forces raid West Bank camp'))
        self.assertFalse(is_escalation('Iraqi oil workers strike at Basra fields'))
        self.assertFalse(is_escalation('Iran strikes deal with China on oil exports'))
        self.assertFalse(is_escalation('Saudi Aramco launches charm offensive with investors'))
        self.assertTrue(is_escalation('Israel strikes Iran oil depot'))


class P2RejectedStaysRejected(unittest.TestCase):
    def test_backup_run_with_new_headline_does_not_revive(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            news = tmp / 'n.json'
            arts = [art('A: missile strike on Iranian terminal', d) for d in THREE]
            news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': arts}))
            run(FETCHED.date(), news, EVENTS, tmp / 'c.csv', tmp / 'none')
            rows = read_candidates(tmp / 'c.csv')
            rows[0]['status'] = 'rejected'
            write_candidates(rows, tmp / 'c.csv')
            arts = [art('B: drones hit Iranian terminal', d, '20261111T060000Z') for d in THREE]
            news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': arts}))
            self.assertEqual(run(FETCHED.date(), news, EVENTS, tmp / 'c.csv', tmp / 'none'), [])
            self.assertEqual(read_candidates(tmp / 'c.csv')[0]['status'], 'rejected')
        finally:
            shutil.rmtree(tmp)


class P2ApprovalsNotCancelled(unittest.TestCase):
    def test_no_shared_concurrency_group_and_retry(self):
        text = (ROOT / '.github' / 'workflows' / 'approve-event.yml').read_text()
        self.assertNotIn('concurrency:', text)
        self.assertIn('for attempt in 1 2 3', text)


class P2OneStoryOneCandidate(unittest.TestCase):
    def test_iran_attack_on_israel_is_one_candidate(self):
        arts = [art('Iranian missile attack on Israel', d) for d in THREE]
        self.assertEqual(len(suggest(arts, date(2026, 11, 11), [])), 1)

    def test_separate_stories_stay_separate(self):
        arts = ([art('Missile strike on Iranian refinery', d) for d in THREE]
                + [art('Houthis attack tanker in Red Sea', d) for d in ('d.com', 'e.com', 'f.com')])
        self.assertEqual(len(suggest(arts, date(2026, 11, 11), [])), 2)


class P3ManualEventIdClash(unittest.TestCase):
    def test_manual_event_with_same_id_is_an_error(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            events = tmp / 'e.csv'
            shutil.copyfile(EVENTS, events)
            with events.open('a', newline='', encoding='utf-8') as h:
                csv.writer(h).writerow(['me-2026-iran-1111', '2026-11-11', 'Manual', 'mideast-conflict',
                                        'Iran', 'manual-ep', 'https://m', 'yes', 'hand-made'])
            news = tmp / 'n.json'
            news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': [
                art('Missile strike hits Iranian oil terminal', d) for d in THREE]}))
            run(FETCHED.date(), news, events, tmp / 'c.csv', tmp / 'none')
            with self.assertRaises(ValueError) as caught:
                approve_event.approve('c-20261111-iran', events=events, candidates=tmp / 'c.csv')
            self.assertIn('already exists', str(caught.exception))
        finally:
            shutil.rmtree(tmp)


class P3MarkdownEscaped(unittest.TestCase):
    def test_title_cannot_inject_a_link(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            write_candidates([{'candidate_id': 'c-20261112-iran', 'date_public': '2026-11-12',
                               'title': 'Iran strike](http://evil.example) [x', 'region': 'iran',
                               'episode_hint': '', 'source_url': 'https://ok.example/a',
                               'n_sites': '3', 'status': 'pending', 'method': 'ai',
                               'event_type': 'airstrike'}], tmp / 'c.csv')
            text = '\n'.join(candidate_lines(date(2026, 11, 12), tmp / 'c.csv', tmp / 'none'))
            self.assertNotIn('](http://evil.example)', text)
            self.assertIn('(https://ok.example/a)', text)
        finally:
            shutil.rmtree(tmp)


class P3WordingAndNaiveTime(unittest.TestCase):
    def test_naive_fetched_at_is_utc_not_a_crash(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            news = tmp / 'n.json'
            news.write_text(json.dumps({'fetched_at': '2026-11-12T06:23:00', 'articles': [
                art('Missile strike hits Iranian oil terminal', d) for d in THREE]}))
            self.assertEqual(len(run(date(2026, 11, 12), news, EVENTS, tmp / 'c.csv', tmp / 'n')), 1)
        finally:
            shutil.rmtree(tmp)

    def test_no_24_hour_wording_left(self):
        for f in ('scripts/daily_report.py', 'src/huginn_muninn/ai_screen.py'):
            self.assertNotIn('24 hours', (ROOT / f).read_text(), f)


if __name__ == '__main__':
    unittest.main()
