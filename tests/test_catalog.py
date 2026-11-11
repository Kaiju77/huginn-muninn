import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.huginn_muninn.catalog import COLUMNS, first_per_episode, load_catalog

ROOT = Path(__file__).resolve().parent.parent
MIDEAST = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
HEADER = ','.join(COLUMNS)
GOOD = 'e1,2020-01-03,T,mideast-conflict,Iraq,ep1,https://example.org/a,no,'


def write(text):
    tmp = tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8')
    tmp.write(text)
    tmp.close()
    return Path(tmp.name)


class RealCatalogTest(unittest.TestCase):
    def test_mideast_catalog_loads(self):
        events = load_catalog(MIDEAST, category='mideast-conflict')
        self.assertGreaterEqual(len(events), 20)
        self.assertEqual(events, sorted(events, key=lambda e: (e.date_public, e.event_id)))
        # EIA daily Brent starts 1987-05-20; earlier events would be skipped.
        self.assertGreaterEqual(events[0].date_public, date(1987, 5, 20))

    def test_episodes_reduce_to_independent_events(self):
        events = load_catalog(MIDEAST)
        firsts = first_per_episode(events)
        self.assertLess(len(firsts), len(events))
        self.assertGreaterEqual(len(firsts), 20)
        self.assertEqual(len({e.episode for e in firsts}), len(firsts))


class ValidationTest(unittest.TestCase):
    def assert_rejected(self, body, message, **kwargs):
        path = write(HEADER + '\n' + body + '\n')
        try:
            with self.assertRaises(ValueError) as caught:
                load_catalog(path, **kwargs)
            self.assertIn(message, str(caught.exception))
        finally:
            path.unlink()

    def test_good_row(self):
        path = write(HEADER + '\n' + GOOD + '\n')
        try:
            [event] = load_catalog(path)
            self.assertEqual(event.to_event().date_public, date(2020, 1, 3))
            self.assertFalse(event.source_checked)
        finally:
            path.unlink()

    def test_rejections(self):
        self.assert_rejected(GOOD + '\n' + GOOD, 'duplicate event_id')
        self.assert_rejected(GOOD.replace('2020-01-03', '03.01.2020'), 'YYYY-MM-DD')
        self.assert_rejected(GOOD.replace('2020-01-03', '2099-01-01'), 'future')
        self.assert_rejected(GOOD.replace('https://', 'http://'), 'https')
        self.assert_rejected(GOOD.replace(',no,', ',maybe,'), 'source_checked')
        self.assert_rejected(GOOD.replace(',ep1,', ',,'), 'episode is empty')
        self.assert_rejected(GOOD, 'is not sanctions', category='sanctions')

    def test_wrong_columns(self):
        path = write('event_id,date\ne1,2020-01-01\n')
        try:
            with self.assertRaises(ValueError):
                load_catalog(path)
        finally:
            path.unlink()


if __name__ == '__main__':
    unittest.main()
