import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import scripts.backtest as bt
from scripts.compare_catalogs import build, md
from src.huginn_muninn.catalog import COLUMNS, CatalogEvent, load_catalog
from src.huginn_muninn.compare import (
    chance_matches, countries_of, coverage_window, episodes, match_episodes)
from src.huginn_muninn.ucdp_events import CATEGORY, Onset, OnsetRule, to_catalog_rows

ROOT = Path(__file__).resolve().parent.parent
HAND = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
IDS = {'Iran': 630, 'Iraq': 645, 'Israel': 666, 'Lebanon': 660, 'Syria': 652, 'Yemen': 678,
       'Saudi Arabia': 670, 'Kuwait': 690, 'Libya': 620}


def ev(i, day, region='Iraq', episode=None, title=None):
    return CatalogEvent(i, date.fromisoformat(day), title or i, 'c', region, episode or i,
                        'https://x', False, '')


def write_rows(path, rows):
    with path.open('w', newline='', encoding='utf-8') as h:
        w = csv.DictWriter(h, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def ucdp_rows(onsets):
    return to_catalog_rows([Onset(IDS[c], c, date.fromisoformat(d), 40) for c, d in onsets],
                           today=date(2026, 11, 12))


class MatchTest(unittest.TestCase):
    def test_nearest_pairs_each_used_once(self):
        hand = episodes([ev('h1', '2020-01-03'), ev('h2', '2020-06-01')])
        ucdp = episodes([ev('u1', '2020-01-05'), ev('u2', '2020-01-04'), ev('u3', '2021-01-01')])
        matches, hand_only, ucdp_only = match_episodes(hand, ucdp)
        self.assertEqual([(m.hand.episode, m.ucdp.episode, m.days_apart) for m in matches],
                         [('h1', 'u2', 1)])
        self.assertEqual([e.episode for e in hand_only], ['h2'])
        self.assertEqual({e.episode for e in ucdp_only}, {'u1', 'u3'})

    def test_window_edge(self):
        one = lambda a, b: len(match_episodes(episodes([ev('h', a)]), episodes([ev('u', b)]))[0])
        self.assertEqual(one('2020-01-01', '2020-01-08'), 1)
        self.assertEqual(one('2020-01-01', '2020-01-09'), 0)

    def test_round12_later_event_of_episode_matches(self):
        # 2006: the Lebanon onset is the 2nd event of a UCDP episode opened by Israel.
        hand = episodes([ev('me-2006-lebanon-war', '2006-07-12', 'Lebanon/Israel')])
        ucdp = episodes(load_rows(ucdp_rows([('Israel', '2006-06-28'), ('Lebanon', '2006-07-07')])))
        matches, hand_only, _ = match_episodes(hand, ucdp)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].ucdp_event.event_id, 'ucdp-2006-lebanon-0707')
        self.assertEqual(hand_only, [])

    def test_round12_hand_second_event_matches(self):
        hand = episodes([ev('me-1990-kuwait', '1990-08-02', 'Kuwait/Iraq', 'gulf'),
                         ev('me-1991-storm', '1991-01-17', 'Iraq', 'gulf')])
        ucdp = episodes([ev('u', '1991-01-18', 'Iraq')])
        self.assertEqual(len(match_episodes(hand, ucdp)[0]), 1)

    def test_round12_country_must_overlap(self):
        hand = episodes([ev('me-1990-kuwait', '1990-08-02', 'Kuwait/Iraq')])
        ucdp = episodes([ev('u', '1990-08-05', 'Israel')])
        self.assertEqual(match_episodes(hand, ucdp)[0], [])
        self.assertEqual(countries_of('Gulf of Oman'), {'Iran', 'Oman', 'United Arab Emirates'})
        self.assertIn('Israel', countries_of('Israel/Gaza'))

    def test_round12_one_close_pair_cannot_block_two(self):
        hand = episodes([ev('h2', '2020-01-01'), ev('h1', '2020-01-07')])
        ucdp = episodes([ev('u1', '2020-01-04'), ev('u2', '2019-12-26')])
        got = {(m.hand.episode, m.ucdp.episode) for m in match_episodes(hand, ucdp)[0]}
        self.assertEqual(got, {('h2', 'u2'), ('h1', 'u1')})

    def test_chance_matches_counts_shifted_agreements(self):
        hand = episodes([ev(f'h{k}', f'{2000 + k}-03-01') for k in range(5)])
        ucdp = episodes([ev(f'u{k}', f'{2000 + k}-03-02') for k in range(5)])
        self.assertEqual(len(match_episodes(hand, ucdp)[0]), 5)
        self.assertLess(chance_matches(hand, ucdp), 1)

    def test_coverage_window(self):
        start, end = coverage_window(OnsetRule(), date(2025, 12, 31))
        self.assertEqual(start, date(1989, 1, 1) + timedelta(days=90 + 7 - 1 + 1))
        self.assertEqual(end, date(2026, 1, 1))


def load_rows(rows):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'u.csv'
        write_rows(path, rows)
        return load_catalog(path)


class ReportTest(unittest.TestCase):
    def build_with(self, onsets, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mideast-conflict-ucdp.csv'
            write_rows(path, ucdp_rows(onsets) if onsets is not None else [])
            return build(HAND, path, ged_path=Path(tmp) / 'none.csv', **kw)

    def test_without_ucdp_file(self):
        text = build(HAND, Path('/nonexistent/ucdp.csv'))
        self.assertIn('does not exist yet', text)
        self.assertIn('UCDP_TOKEN', text)

    def test_round12_header_only_file(self):
        self.assertIn('rule-based list is empty', self.build_with(None))

    def test_realistic_catalog_via_to_catalog_rows(self):
        hand = load_catalog(HAND)
        onsets = [('Israel', '2006-06-28'), ('Lebanon', '2006-07-07'), ('Iraq', '1991-01-16'),
                  ('Iraq', '2003-03-19'), ('Yemen', '2015-03-25'), ('Syria', '2013-08-20'),
                  ('Israel', '2023-10-06'), ('Israel', '1990-08-05'), ('Libya', '2011-02-15')]
        onsets += [('Saudi Arabia', f'{1995 + k}-07-01') for k in range(10)]
        onsets.append(('Iraq', '2024-12-01'))   # last onset: sets the coverage end
        text = self.build_with(onsets)
        agree = text.split('## Agreements')[1].split('##')[0]
        for hid in ('me-2006-lebanon-war', 'me-2003-iraq-invasion', 'me-2015-yemen',
                    'me-1991-desert-storm', 'me-2023-oct-7'):
            self.assertIn(hid, agree)
        self.assertNotIn('ucdp-1990-israel', agree)          # wrong country
        outside = text.split('outside UCDP coverage')[1].split('##')[0]
        for hid in ('me-1988-praying-mantis', 'me-2025-twelve-day-war', 'me-2026-iran-war'):
            self.assertIn(hid, outside)
        self.assertNotIn('me-2026-iran-war', text.split('## Only hand-picked')[1].split('##')[0])
        self.assertIn('from luck alone', text)
        self.assertIn('fixed rule applied to UCDP data', text)
        self.assertNotIn('picked by hand with hindsight', text.split('## Backtest, rule-based')[1])
        self.assertEqual(len(hand), len(load_catalog(HAND)))

    def test_round12_no_price_files(self):
        with tempfile.TemporaryDirectory() as empty:
            text = self.build_with([('Iraq', '2003-03-19')] * 1, prices_dir=Path(empty))
        self.assertIn('No price files found.', text)
        self.assertIn('Too few events', text)

    def test_round12_markdown_escaping(self):
        self.assertEqual(md('a\n\n## Base rates|x'), 'a ## Base rates/x')
        self.assertEqual(md('## fake'), 'fake')
        self.assertNotIn('<', md('<script>'))


class BacktestCliTest(unittest.TestCase):
    def test_other_catalog_never_overwrites_main_report(self):
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

    def test_round12_list_note_by_category(self):
        hand = load_catalog(HAND)
        self.assertIn('picked by hand', bt.list_note(hand))
        self.assertIn('revises its death counts',
                      bt.list_note([e._replace(category=CATEGORY) for e in hand]))
        self.assertIn('Check how', bt.list_note([e._replace(category='other') for e in hand]))

    def test_round12_missing_events_file_is_clean_error(self):
        with self.assertRaises(SystemExit) as cm:
            bt.main(['--events', '/nonexistent.csv'])
        self.assertEqual(cm.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
