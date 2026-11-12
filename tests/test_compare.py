import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts.compare_catalogs import build
from src.huginn_muninn.catalog import COLUMNS, CatalogEvent, load_catalog
from src.huginn_muninn.compare import match_events

ROOT = Path(__file__).resolve().parent.parent
HAND = ROOT / 'data' / 'events' / 'mideast-conflict.csv'


def ev(i, day, episode=None):
    return CatalogEvent(i, date.fromisoformat(day), i, 'c', 'r', episode or i, 'https://x', False, '')


class MatchTest(unittest.TestCase):
    def test_nearest_pairs_each_used_once(self):
        hand = [ev('h1', '2020-01-03'), ev('h2', '2020-06-01')]
        ucdp = [ev('u1', '2020-01-05'), ev('u2', '2020-01-04'), ev('u3', '2021-01-01')]
        matches, hand_only, ucdp_only = match_events(hand, ucdp)
        self.assertEqual([(m.hand_id, m.ucdp_id, m.days_apart) for m in matches], [('h1', 'u2', 1)])
        self.assertEqual([e.event_id for e in hand_only], ['h2'])
        self.assertEqual({e.event_id for e in ucdp_only}, {'u1', 'u3'})

    def test_window_edge(self):
        self.assertEqual(len(match_events([ev('h', '2020-01-01')], [ev('u', '2020-01-08')])[0]), 1)
        self.assertEqual(len(match_events([ev('h', '2020-01-01')], [ev('u', '2020-01-09')])[0]), 0)


class ReportTest(unittest.TestCase):
    def test_without_ucdp_file(self):
        text = build(HAND, Path('/nonexistent/ucdp.csv'))
        self.assertIn('does not exist yet', text)
        self.assertIn('UCDP_TOKEN', text)

    def test_with_synthetic_ucdp_catalog(self):
        # Synthetic rule-based catalog: half of the hand-picked dates shifted by 1 day,
        # plus extra onsets, in the UCDP category.
        hand = load_catalog(HAND)
        rows = []
        for k, e in enumerate(hand[::2]):
            d = e.date_public + timedelta(days=1)
            rows.append([f'ucdp-{d.year}-x-{k}', d.isoformat(), f'Onset {k}', 'mideast-conflict-ucdp',
                         'Iraq', f'ucdp-ep-{k}', 'https://ucdp.uu.se/', 'no', 'synthetic'])
        for k in range(10):
            d = date(1995 + k, 7, 1)
            rows.append([f'ucdp-extra-{k}', d.isoformat(), f'Extra {k}', 'mideast-conflict-ucdp',
                         'Syria', f'ucdp-extra-ep-{k}', 'https://ucdp.uu.se/', 'no', 'synthetic'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ucdp.csv'
            with path.open('w', newline='', encoding='utf-8') as h:
                w = csv.writer(h)
                w.writerow(COLUMNS)
                w.writerows(sorted(rows, key=lambda r: r[1]))
            text = build(HAND, path)
        self.assertIn('## Matched', text)
        for k in range(10):
            self.assertIn(f'ucdp-extra-{k} (', text.split('## Only rule-based')[1].split('##')[0])
        self.assertIn('fixed rule, not hand-picking', text)
        self.assertNotIn('picked by hand with hindsight', text.split('## Backtest, rule-based list')[1])
        self.assertIn('## Base rates, rule-based list', text)
        self.assertIn('95% CI', text)
        self.assertIn('## Backtest, rule-based list', text)
        self.assertIn('not a forecast or advice', text)


class BacktestCliTest(unittest.TestCase):
    def test_other_catalog_never_overwrites_main_report(self):
        import scripts.backtest as bt
        with tempfile.TemporaryDirectory() as tmp:
            old = bt.OUT
            bt.OUT = Path(tmp) / 'calibration.md'
            try:
                bt.main(['--events', str(HAND)])
                self.assertTrue(bt.OUT.exists())
                bt.OUT.unlink()
                other = Path(tmp) / 'other.csv'
                other.write_text(HAND.read_text(encoding='utf-8'), encoding='utf-8')
                bt.main(['--events', str(other)])
                self.assertFalse(bt.OUT.exists())
                self.assertTrue((Path(tmp) / 'calibration-other.md').exists())
            finally:
                bt.OUT = old


if __name__ == '__main__':
    unittest.main()
