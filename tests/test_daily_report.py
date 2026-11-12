import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.daily_report import build
from scripts.fetch_news import parse, url
from scripts.fetch_prices import write_csv
from src.huginn_muninn import daily
from src.huginn_muninn.study import Close

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def weekdays(start, count):
    out, d = [], start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class MoveTest(unittest.TestCase):
    def test_changes_and_rank(self):
        days = weekdays(date(2020, 1, 1), 300)
        values = [100.0 + (i % 2) * 0.1 for i in range(299)] + [120.0]  # last day jumps
        closes = [Close(d, v) for d, v in zip(days, values)]
        m = daily.move('X', 'u', closes)
        self.assertAlmostEqual(m.change_1d, 120 / values[-2] - 1)
        self.assertAlmostEqual(m.change_5d, 120 / values[-6] - 1)
        self.assertEqual(m.rank_1d, 1.0)  # bigger than every earlier day

    def test_short_history(self):
        m = daily.move('X', 'u', [Close(date(2020, 1, 1), 5.0)])
        self.assertIsNone(m.change_1d)
        self.assertIsNone(m.rank_1d)


class HeadlinesTest(unittest.TestCase):
    def test_dedupe_and_order(self):
        arts = [{'title': 'Oil A', 'seendate': '20261110T100000Z', 'url': 'u1', 'domain': 'd'},
                {'title': 'oil a', 'seendate': '20261110T090000Z', 'url': 'u2', 'domain': 'd'},
                {'title': 'Iran B', 'seendate': '20261110T110000Z', 'url': 'u3', 'domain': 'd'},
                {'title': '', 'seendate': '20261110T120000Z', 'url': 'u4', 'domain': 'd'}]
        self.assertEqual([h[0] for h in daily.headlines(arts)], ['Iran B', 'Oil A'])

    def test_off_topic_headlines_dropped(self):
        arts = [{'title': 'Sensex zooms 1,100 pts on global cues', 'seendate': '1', 'url': 'u', 'domain': 'd'},
                {'title': 'Tanker involved in incident in Strait of Hormuz', 'seendate': '2',
                 'url': 'u', 'domain': 'd'},
                {'title': 'Asian shares rise on AI chip demand', 'seendate': '3', 'url': 'u', 'domain': 'd'}]
        self.assertEqual([h[0] for h in daily.headlines(arts)],
                         ['Tanker involved in incident in Strait of Hormuz'])

    def test_gdelt_parse_and_url(self):
        body = json.dumps({'articles': [{'title': 'T', 'url': 'https://x', 'domain': 'x',
                                         'seendate': '20261110T100000Z', 'extra': 1}]}).encode()
        self.assertEqual(parse(body)[0]['title'], 'T')
        self.assertNotIn('extra', parse(body)[0])
        self.assertIn('mode=ArtList', url())
        self.assertIn('timespan=1d', url())


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        days = weekdays(date(1987, 5, 20), 10200)
        write_csv([(d, 50 + i * 0.001) for i, d in enumerate(days)],
                  self.dir / 'brent.csv', 'USD/barrel')
        self.news = self.dir / 'news.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_look_ahead_for_a_past_date(self):
        text = build(date(2026, 3, 20), self.dir, EVENTS, self.news)
        self.assertIn('| Brent | 2026-03-20 |', text)
        self.assertIn('2026 Iran war begins (2026-02-28)', text)
        self.assertIn('14 trading days since the news', text)  # Mon 2 Mar to Fri 20 Mar

    def test_recent_event_uses_only_earlier_comparables_and_shows_ci(self):
        text = build(date(2026, 3, 20), self.dir, EVENTS, self.news)
        self.assertIn('in 20 comparable events', text)  # 21 episodes minus its own
        self.assertIn('95% CI', text)
        self.assertIn('Baseline', text)

    def test_quiet_day_and_missing_inputs(self):
        text = build(date(2026, 11, 11), self.dir, EVENTS, self.news)
        self.assertIn('No catalog events in the last 90 days', text)
        self.assertIn('| WTI | no data yet', text)
        self.assertIn('News unavailable.', text)
        self.assertIn('Not a forecast or advice', text)

    def write_news(self, fetched_at, titles=('Tanker hit [update]',)):
        self.news.write_text(json.dumps({
            'fetched_at': fetched_at.isoformat(),
            'articles': [{'title': x, 'url': f'https://n/{i}', 'domain': 'n',
                          'seendate': '20261111T060000Z'} for i, x in enumerate(titles)]}))

    def test_headlines_fetched_today_are_shown(self):
        self.write_news(datetime(2026, 11, 11, 6, 30, tzinfo=timezone.utc))
        text = build(date(2026, 11, 11), self.dir, EVENTS, self.news)
        self.assertIn('- [Tanker hit (update)](https://n/0) (n)', text)
        self.assertIn('Fetched 2026-11-11 06:30 UTC', text)


class CodexRound4Test(unittest.TestCase):
    """Regression tests for the 2026-11-11 Codex review, round 4."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        days = weekdays(date(1987, 5, 20), 10200)
        write_csv([(d, 50 + i * 0.001) for i, d in enumerate(days)],
                  self.dir / 'brent.csv', 'USD/barrel')
        self.news = self.dir / 'news.json'
        self.news.write_text(json.dumps({
            'fetched_at': '2026-11-11T06:30:00+00:00',
            'articles': [{'title': 'November headline', 'url': 'https://n/1',
                          'domain': 'n', 'seendate': '20261111T060000Z'}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_1_past_brief_shows_no_future_headlines(self):
        text = build(date(2026, 3, 20), self.dir, EVENTS, self.news)
        self.assertNotIn('November headline', text)
        self.assertIn('No headlines fetched on 2026-03-20', text)

    def test_2_quiet_day_fallback_has_no_future_events(self):
        text = build(date(1980, 1, 1), self.dir, EVENTS, self.news)
        self.assertNotIn('2026', text.split('## Recent events')[1].split('## Headlines')[0])

    def test_3_failed_refresh_today_is_reported(self):
        text = build(date(2026, 11, 12), self.dir, EVENTS, self.news)  # yesterday's cache
        self.assertNotIn('November headline', text)
        self.assertIn("today's fetch failed or has not run", text)

    def test_4_empty_or_malformed_gdelt_is_a_failure(self):
        for body in (b'', b'{}', b'{"error":"backend unavailable"}',
                     b'{"articles": []}', b'{"articles": "x"}', b'[]'):
            with self.assertRaises(ValueError, msg=body):
                parse(body)


if __name__ == '__main__':
    unittest.main()
