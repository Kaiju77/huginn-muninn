"""Regression tests for review round 9 (independent reviewer, Fable 5.2, 2026-11-12)."""

import http.server
import json
import shutil
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import fetch_ucdp, prediction_log
from scripts.suggest_events import read_candidates, run as suggest_run, write_candidates
from src.huginn_muninn import predictions as pr
from src.huginn_muninn.candidates import is_escalation
from src.huginn_muninn.catalog import load_catalog
from src.huginn_muninn.ucdp_events import GedRow, find_onsets

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


class F1NoFakeLiveBackfill(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_past_today_refused_without_backfill(self):
        with self.assertRaises(prediction_log.BackfillRefused):
            prediction_log.run(date(2025, 6, 25), self.tmp / 'l.csv', self.tmp / 'r.md',
                               now=date(2026, 11, 12))

    def test_backfill_never_writes_the_live_log(self):
        with self.assertRaises(prediction_log.BackfillRefused):
            prediction_log.run(date(2025, 6, 25), prediction_log.LOG, self.tmp / 'r.md',
                               allow_backfill=True, now=date(2026, 11, 12))

    def test_today_before_newest_row_refused(self):
        log = self.tmp / 'l.csv'
        prediction_log.run(date(2025, 6, 16), log, self.tmp / 'r.md', allow_backfill=True,
                           now=date(2026, 11, 12))
        self.assertGreater(len(prediction_log.read_log(log)), 0)
        with self.assertRaises(prediction_log.BackfillRefused):
            prediction_log.run(date(2025, 6, 15), log, self.tmp / 'r.md', allow_backfill=True,
                               now=date(2026, 11, 12))

    def test_cli_refuses(self):
        self.assertEqual(prediction_log.main(['--today', '2025-06-25']), 2)


class F2OnePredictionPerCrisis(unittest.TestCase):
    def test_follow_up_event_in_same_episode_not_predicted(self):
        catalog = load_catalog(EVENTS)
        recent = [e for e in catalog if e.episode == '2025-twelve-day-war']
        self.assertEqual(len(recent), 2)
        firsts = pr.first_of_episodes(recent, catalog)
        self.assertEqual([e.event_id for e in firsts], ['me-2025-twelve-day-war'])

    def test_backfill_has_one_event_per_episode(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            # 23 June: both events of the episode are recent and young enough.
            rows, _ = prediction_log.run(date(2025, 6, 23), tmp / 'l.csv', tmp / 'r.md',
                                         allow_backfill=True, now=date(2026, 11, 12))
            self.assertEqual({r.event_id for r in rows}, {'me-2025-twelve-day-war'})
        finally:
            shutil.rmtree(tmp)


class F3NoLateRecording(unittest.TestCase):
    def test_entry_older_than_limit_not_recorded(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            # 12 days after the 2025-06-13 event: entry close is too old.
            rows, _ = prediction_log.run(date(2025, 6, 25), tmp / 'l.csv', tmp / 'r.md',
                                         allow_backfill=True, now=date(2026, 11, 12))
            self.assertEqual(rows, [])
            rows, _ = prediction_log.run(date(2025, 6, 16), tmp / 'l2.csv', tmp / 'r2.md',
                                         allow_backfill=True, now=date(2026, 11, 12))
            self.assertTrue(rows)
            self.assertTrue(all((date(2025, 6, 16) - r.entry_date).days <= pr.MAX_ENTRY_AGE_DAYS
                                for r in rows if r.entry_date))
        finally:
            shutil.rmtree(tmp)


class F4CeasefireDealIsStillAStrike(unittest.TestCase):
    def test_reviewer_examples(self):
        for title in ('Israel strikes Gaza despite ceasefire deal',
                      'Israel strikes Lebanon despite ceasefire agreement',
                      'Israel strikes Iran after nuclear deal collapses'):
            self.assertTrue(is_escalation(title), title)
        self.assertFalse(is_escalation('Qatar strikes $20bn LNG supply deal'))


class F5SameStoryAcrossDays(unittest.TestCase):
    def test_reviewer_example(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            news, cands = tmp / 'n.json', tmp / 'c.csv'

            def art(i, seen):
                return {'title': f'Israeli strike on Gaza port {i}', 'domain': f's{i}',
                        'seendate': seen, 'url': f'https://s{i}/x'}
            day1 = [art(i, '20261109T190000Z') for i in range(1, 7)]
            news.write_text(json.dumps({'fetched_at': '2026-11-10T06:23:00+00:00', 'articles': day1}))
            suggest_run(date(2026, 11, 10), news, EVENTS, cands, tmp / 'none')
            day2 = day1 + [art(i, '20261110T200000Z') for i in range(7, 10)]
            news.write_text(json.dumps({'fetched_at': '2026-11-11T06:23:00+00:00', 'articles': day2}))
            suggest_run(date(2026, 11, 11), news, EVENTS, cands, tmp / 'none')
            day3 = [art(i, '20261110T200000Z') for i in range(7, 10)]
            news.write_text(json.dumps({'fetched_at': '2026-11-12T06:23:00+00:00', 'articles': day3}))
            suggest_run(date(2026, 11, 12), news, EVENTS, cands, tmp / 'none')
            self.assertEqual(len(read_candidates(cands)), 1)
        finally:
            shutil.rmtree(tmp)


class _Redirect(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        _Redirect.seen.append(self.headers.get(fetch_ucdp.TOKEN_HEADER))
        if self.path.startswith('/a'):
            self.send_response(302)
            self.send_header('Location', f'http://127.0.0.1:{self.server.server_port}/b')
            self.end_headers()
        elif self.path.startswith('/short'):
            self.send_response(200)
            self.send_header('Content-Length', '100')
            self.end_headers()
            self.wfile.write(b'{')
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')

    def log_message(self, *a):
        pass


class F6F7UcdpHttp(unittest.TestCase):
    def setUp(self):
        _Redirect.seen = []
        self.server = http.server.HTTPServer(('127.0.0.1', 0), _Redirect)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()

    def test_redirect_refused_token_not_forwarded(self):
        with self.assertRaises(RuntimeError) as caught:
            fetch_ucdp.http_get(self.base + '/a', 'SECRET-TOKEN', retries=1)
        self.assertIn('redirect refused', str(caught.exception))
        self.assertEqual(_Redirect.seen, ['SECRET-TOKEN'])  # only the first host saw it
        self.assertNotIn('SECRET', str(caught.exception))

    def test_truncated_body_is_a_clean_error(self):
        with self.assertRaises(RuntimeError) as caught:
            fetch_ucdp.http_get(self.base + '/short', 't', retries=1)
        self.assertIn('IncompleteRead', str(caught.exception))


class F8DamagedLogIsVisible(unittest.TestCase):
    def test_workflow_flags_prediction_log_failure(self):
        text = (ROOT / '.github' / 'workflows' / 'fetch-prices.yml').read_text()
        self.assertNotIn('prediction_log.py > /dev/null || true', text)
        self.assertIn('touch /tmp/predlog_failed', text)
        self.assertIn('Fail the run if the prediction log failed', text)


class F9SportAndPriceVerbs(unittest.TestCase):
    def test_reviewer_examples(self):
        for title in ('Ronaldo strikes twice as Al-Nassr win in Riyadh',
                      'Iran strikes gold at Asian Games',
                      'Oil price rockets as Iran tensions rise'):
            self.assertFalse(is_escalation(title), title)
        self.assertTrue(is_escalation('Rockets fired at Israel from Lebanon'))
        self.assertTrue(is_escalation('Hezbollah rocket attack on Haifa'))


def ged(day, best, prec=1, cid=645, start=None):
    d = date.fromisoformat(day)
    s = date.fromisoformat(start) if start else d
    return GedRow(id=hash((day, best, prec)) & 0xFFFF, date_start=s, date_end=d, date_prec=prec,
                  country='Iraq', country_id=cid, region='Middle East', type_of_violence=1,
                  best=best)


class F10F11UcdpRule(unittest.TestCase):
    def test_first_allowed_onset_accounts_for_window(self):
        self.assertEqual(find_onsets([ged('1989-04-06', 30)]), [])
        self.assertEqual(len(find_onsets([ged('1989-04-07', 30)])), 1)

    def test_imprecise_row_blocks_a_false_calm(self):
        rows = [ged('2000-01-31', 1000, prec=4, start='2000-01-01'), ged('2000-02-10', 30)]
        self.assertEqual(find_onsets(rows), [])
        self.assertEqual(len(find_onsets([ged('2000-02-10', 30)])), 1)


if __name__ == '__main__':
    unittest.main()
