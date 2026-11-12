"""Regression tests for the 2026-11-12 Codex review, round 5 (one per finding)."""

import csv
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

from scripts import approve_event
from scripts.ai_screen import screen
from scripts.daily_report import build
from scripts.fetch_news import parse as parse_gdelt
from scripts.suggest_events import read_candidates, run
from src.huginn_muninn.ai_screen import numbered, parse
from src.huginn_muninn.candidates import suggest
from src.huginn_muninn.catalog import load_catalog
from src.huginn_muninn.daily import in_window, relevant

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
ON = date(2026, 11, 11)
FETCHED = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def art(title, domain, seen='20261111T080000Z'):
    return {'title': title, 'domain': domain, 'seendate': seen, 'url': f'https://{domain}/x'}


IRAN_ATTACK = [art('Missile strike hits Iranian oil terminal', 'a.com'),
               art('Iran oil terminal attacked by drones', 'b.com'),
               art('Explosions at Iranian oil terminal after strike', 'c.com')]


class Finding1OldAndFutureArticles(unittest.TestCase):
    def test_window_drops_old_future_and_undated(self):
        arts = [art('Oil now', 'a.com'), art('Oil 2020', 'b.com', '20200101T080000Z'),
                art('Oil 2099', 'c.com', '20990101T080000Z'), art('Oil undated', 'd.com', '')]
        self.assertEqual([a['title'] for a in in_window(arts, FETCHED)], ['Oil now'])

    def test_old_articles_never_become_a_candidate(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            old = [dict(a, seendate='20200101T080000Z') for a in IRAN_ATTACK]
            news = tmp / 'n.json'
            news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': old}))
            self.assertEqual(run(ON, news, EVENTS, tmp / 'c.csv', tmp / 'none.json'), [])
            text = build(ON, ROOT / 'data' / 'prices', EVENTS, news,
                         candidates_path=tmp / 'c.csv', ai_path=tmp / 'none.json')
            self.assertNotIn('Missile strike', text)
        finally:
            shutil.rmtree(tmp)


class Finding2MalformedGdelt(unittest.TestCase):
    def test_null_or_empty_articles_are_a_failure(self):
        for body in (b'{"articles":[null]}', b'{"articles":[{}]}',
                     b'{"articles":[{"title":"","url":"https://x"}]}',
                     b'{"articles":[{"title":"Oil","url":""}]}'):
            with self.assertRaises(ValueError, msg=body):
                parse_gdelt(body)


class Finding3AiCitations(unittest.TestCase):
    def setUp(self):
        self.items = numbered(IRAN_ATTACK, FETCHED)

    def p(self, ev):
        return parse(json.dumps({'events': [ev]}), self.items, ON, [])

    def test_codex_example_libya_on_iran_headlines_rejected(self):
        cands, notes, rejected = self.p({
            'title': 'Libya invaded today', 'region': 'libya', 'event_type': 'invasion',
            'headlines': [1, 2, 999], 'happened_today': True, 'relevance': 'high'})
        self.assertEqual((cands, rejected), ([], 1))

    def test_any_nonexistent_citation_rejects(self):
        _, _, rejected = self.p({
            'title': 'Strike on Iranian terminal', 'region': 'iran', 'event_type': 'airstrike',
            'headlines': [1, 2, 999], 'happened_today': True, 'relevance': 'high'})
        self.assertEqual(rejected, 1)

    def test_region_must_appear_in_cited_headlines(self):
        _, _, rejected = self.p({
            'title': 'Iraq strike', 'region': 'iraq', 'event_type': 'airstrike',
            'headlines': [1, 2, 3], 'happened_today': True, 'relevance': 'high'})
        self.assertEqual(rejected, 1)

    def test_valid_event_still_passes(self):
        cands, _, rejected = self.p({
            'title': 'Strike on Iranian oil terminal', 'region': 'iran', 'event_type': 'airstrike',
            'headlines': [1, 2, 3], 'happened_today': True, 'relevance': 'high'})
        self.assertEqual((len(cands), rejected), (1, 0))


class Finding4RejectedAiKeepsKeywordFallback(unittest.TestCase):
    def test_codex_example_mars_region(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            news = {'fetched_at': FETCHED.isoformat(), 'articles': IRAN_ATTACK}
            status = screen(news, 't', [], call=lambda m, msgs, tok: json.dumps({'events': [{
                'title': 'x', 'region': 'mars', 'event_type': 'attack', 'headlines': [1, 2],
                'happened_today': True, 'relevance': 'high'}]}))
            self.assertTrue(status['ok'])
            self.assertEqual(status['rejected'], 1)
            (tmp / 'ai.json').write_text(json.dumps(status))
            (tmp / 'n.json').write_text(json.dumps(news))
            new = run(ON, tmp / 'n.json', EVENTS, tmp / 'c.csv', tmp / 'ai.json')
            self.assertEqual([(c['region'], c['method']) for c in new], [('iran', 'keyword')])
        finally:
            shutil.rmtree(tmp)


class Finding5TimeoutFallsBack(unittest.TestCase):
    def test_subprocess_timeout_gives_ok_false_not_a_crash(self):
        def slow(model, msgs, token):
            raise subprocess.TimeoutExpired('curl', 150)
        news = {'fetched_at': FETCHED.isoformat(), 'articles': IRAN_ATTACK}
        with mock.patch('scripts.ai_screen.time.sleep'):
            status = screen(news, 't', [], call=slow)
        self.assertFalse(status['ok'])
        self.assertIn('TimeoutExpired', status['error'])

    def test_workflow_ai_step_cannot_stop_the_job(self):
        text = (ROOT / '.github' / 'workflows' / 'fetch-prices.yml').read_text()
        step = text[text.index('AI screen of headlines'):text.index('Suggest new events')]
        self.assertIn('continue-on-error: true', step)


class Finding6KeywordVocabulary(unittest.TestCase):
    def test_attacking_and_yemeni(self):
        arts = [art('Iran is attacking oil terminal', d) for d in ('a.com', 'b.com', 'c.com')]
        self.assertEqual([c.region for c in suggest(arts, ON, [])], ['iran'])
        arts = [art('Yemeni forces launch missiles at tanker', d) for d in ('a.com', 'b.com', 'c.com')]
        self.assertEqual([c.region for c in suggest(arts, ON, [])], ['yemen-red-sea'])
        self.assertTrue(relevant('Yemeni forces launch missiles'))


class Finding7NonMilitary(unittest.TestCase):
    def test_codex_example_football(self):
        arts = [art('Iran football team launches offensive against Qatar', d)
                for d in ('a.com', 'b.com', 'c.com')]
        self.assertEqual(suggest(arts, ON, []), [])


class Finding8NorwegianSupplyNews(unittest.TestCase):
    def test_codex_example_equinor(self):
        self.assertTrue(relevant('Equinor shuts Johan Sverdrup after power failure'))
        self.assertTrue(relevant('Norway gas exports cut by North Sea outage'))
        self.assertFalse(relevant('Asian shares rise on AI chip demand'))


class Finding9AtomicApproval(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.events = self.tmp / 'events.csv'
        shutil.copyfile(EVENTS, self.events)
        self.cands = self.tmp / 'cands.csv'
        news = self.tmp / 'n.json'
        news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': IRAN_ATTACK}))
        run(ON, news, self.events, self.cands, self.tmp / 'none.json')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_interrupted_catalog_write_leaves_old_catalog(self):
        original = self.events.read_bytes()
        with mock.patch('scripts.approve_event.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                approve_event.approve('c-20261111-iran', events=self.events, candidates=self.cands)
        self.assertEqual(self.events.read_bytes(), original)
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.suffix == '.tmp'], [])

    def test_retry_after_failed_status_write_completes(self):
        real = approve_event._atomic_write_candidates
        with mock.patch('scripts.approve_event._atomic_write_candidates',
                        side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                approve_event.approve('c-20261111-iran', events=self.events, candidates=self.cands)
        self.assertEqual(read_candidates(self.cands)[0]['status'], 'pending')  # event added
        row = approve_event.approve('c-20261111-iran', events=self.events, candidates=self.cands)
        self.assertEqual(row['event_id'], 'me-2026-iran-1111')
        self.assertEqual(read_candidates(self.cands)[0]['status'], 'approved')
        ids = [e.event_id for e in load_catalog(self.events)]
        self.assertEqual(ids.count('me-2026-iran-1111'), 1)
        self.assertIs(approve_event._atomic_write_candidates, real)


class RejectedIdDoesNotBlockNewSuggestion(unittest.TestCase):
    def test_rejected_keyword_candidate_is_replaced_by_new_ai_candidate(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            news = tmp / 'n.json'
            news.write_text(json.dumps({'fetched_at': FETCHED.isoformat(), 'articles': IRAN_ATTACK}))
            cands = tmp / 'c.csv'
            run(ON, news, EVENTS, cands, tmp / 'none.json')
            rows = read_candidates(cands)
            rows[0]['status'] = 'rejected'
            from scripts.suggest_events import write_candidates
            write_candidates(rows, cands)
            ai = tmp / 'ai.json'
            ai.write_text(json.dumps({'date': ON.isoformat(), 'ok': True, 'rejected': 0,
                                      'candidates': [dict(rows[0], title='Different AI title',
                                                          status='pending')]}))
            new = run(ON, news, EVENTS, cands, ai)
            self.assertEqual(len(new), 1)
            row = read_candidates(cands)[0]
            self.assertEqual((row['status'], row['title'], row['method']),
                             ('pending', 'Different AI title', 'ai'))
            self.assertEqual(run(ON, news, EVENTS, cands, ai), [])  # no churn on rerun
        finally:
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
