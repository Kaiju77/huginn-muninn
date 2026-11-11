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


class CodexRound2Test(unittest.TestCase):
    """Regression tests for the 2026-11-11 Codex review, round 2."""

    def load(self, text):
        path = write(text)
        try:
            return load_catalog(path)
        finally:
            path.unlink()

    def test_4_extra_field_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.load(HEADER + '\n' + GOOD + ',unexpected\n')
        self.assertIn('expected 9 fields', str(caught.exception))

    def test_4_missing_field_rejected(self):
        with self.assertRaises(ValueError) as caught:
            self.load(HEADER + '\n' + GOOD[:-1] + '\n')
        self.assertIn('expected 9 fields', str(caught.exception))

    def test_4_unterminated_quote_rejected(self):
        with self.assertRaises(ValueError):
            self.load(HEADER + '\n' + GOOD + '"unterminated note\n')

    def test_5_utf8_bom_accepted(self):
        [event] = self.load('﻿' + HEADER + '\n' + GOOD + '\n')
        self.assertEqual(event.event_id, 'e1')

    def test_quoted_comma_in_notes_still_fine(self):
        [event] = self.load(HEADER + '\n' + GOOD + '"a, b"\n')
        self.assertEqual(event.notes, 'a, b')

    def test_1_2_3_catalog_corrections(self):
        events = {e.event_id: e for e in load_catalog(MIDEAST)}
        self.assertEqual(events['me-1998-desert-fox'].date_public, date(1998, 12, 17))
        self.assertEqual(events['me-2011-libya-uprising'].date_public, date(2011, 2, 16))
        self.assertEqual(events['me-1990-kuwait-invasion'].episode,
                         events['me-1991-desert-storm'].episode)
        firsts = [e.event_id for e in first_per_episode(load_catalog(MIDEAST))]
        self.assertIn('me-1990-kuwait-invasion', firsts)
        self.assertNotIn('me-1991-desert-storm', firsts)
