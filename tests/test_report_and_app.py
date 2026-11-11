import unittest
from datetime import date, timedelta
from pathlib import Path

from src.huginn_muninn import report
from src.huginn_muninn.catalog import first_per_episode, load_catalog
from src.huginn_muninn.study import Close

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def rising(start, count):
    out, d, i = [], start, 0
    while len(out) < count:
        if d.weekday() < 5:
            out.append(Close(d, 50 + i * 0.01))
            i += 1
        d += timedelta(days=1)
    return out


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.closes = rising(date(1987, 5, 20), 10500)
        self.events = first_per_episode(load_catalog(EVENTS))

    def test_base_rate_rows_have_n_ci_range_and_baseline(self):
        rows = report.base_rate_rows(report.study(self.events, self.closes, 'after_news'))
        self.assertEqual([r['horizon (trading days)'] for r in rows], [5, 20, 60])
        for r in rows:
            self.assertEqual(r['events n'], len(self.events))
            self.assertEqual(r['share rose %'], 100.0)
            self.assertIsNotNone(r['95% CI %'])
            self.assertIsNotNone(r['range %'])
            self.assertIsNotNone(r['baseline 95% CI %'])

    def test_too_few_events_hide_share_and_ci(self):
        rows = report.base_rate_rows(report.study(self.events[:3], self.closes, 'after_news'))
        self.assertIsNone(rows[0]['share rose %'])
        self.assertIsNone(rows[0]['95% CI %'])
        self.assertEqual(rows[0]['events n'], 3)

    def test_event_rows_and_paths(self):
        rows = report.event_rows(self.events, self.closes, (5, 20), 'after_news')
        self.assertEqual(len(rows), len(self.events))
        self.assertTrue(all(r['source'].startswith('https://') for r in rows))
        self.assertGreater(rows[0]['5d %'], 0)
        paths = report.paths(self.events, self.closes, 10, 'after_news')
        self.assertEqual(len(paths), len(self.events))
        first = next(iter(paths.values()))
        self.assertEqual(first[0], (0, 0.0))
        self.assertEqual(len(first), 11)


try:
    from streamlit.testing.v1 import AppTest
except ImportError:  # the CI test job is standard library only
    AppTest = None


@unittest.skipIf(AppTest is None, 'streamlit not installed')
class AppSmokeTest(unittest.TestCase):
    def test_page_renders_without_errors(self):
        app = AppTest.from_file(str(ROOT / 'app' / 'streamlit_app.py'), default_timeout=60)
        app.run()
        self.assertEqual(len(app.exception), 0, app.exception)
        self.assertIn('Middle East conflicts', app.title[0].value)
        self.assertGreaterEqual(len(app.dataframe), 2)
        app.sidebar.radio[0].set_value(app.sidebar.radio[0].options[1]).run()
        self.assertEqual(len(app.exception), 0, app.exception)


if __name__ == '__main__':
    unittest.main()
