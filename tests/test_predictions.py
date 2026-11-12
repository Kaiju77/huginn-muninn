import math
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from scripts import prediction_log as script
from src.huginn_muninn import daily
from src.huginn_muninn import predictions as pr
from src.huginn_muninn.catalog import COLUMNS as CATALOG_COLUMNS, CatalogEvent
from src.huginn_muninn.study import Close


def weekdays(start, count):
    out, d = [], start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = weekdays(date(2015, 1, 1), 1600)   # runs to about 2021-02
CLOSES = [Close(d, 60 + 10 * math.sin(i / 9) + i * 0.01) for i, d in enumerate(DAYS)]


def ev(event_id, day, episode=None):
    return CatalogEvent(event_id, day, f'Event {event_id}', 'mideast-conflict', 'Gulf',
                        episode or event_id, 'https://example.org/' + event_id, True, '')


# Ten comparable past events, each its own episode, then the live event.
PAST = [ev(f'past-{k}', DAYS[60 + 100 * k]) for k in range(10)]
LIVE_DAY = DAYS[1500]
LIVE = ev('live', LIVE_DAY)
CATALOG = PAST + [LIVE]


def comp(e):
    return pr.comparables(CATALOG, e)


def nth_after(day, k):
    """The k-th trading day after ``day`` in DAYS."""
    return DAYS[DAYS.index(day) + k]


class RecordTest(unittest.TestCase):
    def test_same_numbers_as_the_brief(self):
        rows = pr.record([], LIVE_DAY, [LIVE], comp, {'brent': CLOSES})
        self.assertEqual([r.horizon for r in rows], [5, 20, 60])
        known = [c for c in CLOSES if c.on <= LIVE_DAY]
        ctx = daily.event_context(LIVE, comp(LIVE), known)
        for r, res in zip(rows, ctx.results):
            self.assertEqual((r.n, r.rises, r.p_rose, r.ci_low, r.ci_high, r.median),
                             (res.events.n, res.events.rises, res.events.share,
                              res.events.ci_low, res.events.ci_high, res.events.median))
            self.assertEqual((r.low, r.high), (res.events.low, res.events.high))
            self.assertEqual((r.baseline_p, r.baseline_n, r.baseline_rises),
                             (res.baseline.share, res.baseline.n, res.baseline.rises))
            self.assertEqual(r.n, 10)
            self.assertEqual((r.entry_date, r.status, r.made_on), (LIVE_DAY, 'open', LIVE_DAY))

    def test_no_look_ahead(self):
        full = pr.record([], LIVE_DAY, [LIVE], comp, {'brent': CLOSES})
        cut = pr.record([], LIVE_DAY, [LIVE], comp,
                        {'brent': [c for c in CLOSES if c.on <= LIVE_DAY]})
        self.assertEqual(full, cut)
        # Later closes must not score anything either.
        self.assertEqual(pr.score(full, {'brent': CLOSES}, LIVE_DAY), full)

    def test_comparables_exclude_later_and_same_episode(self):
        same = ev('same-episode', DAYS[1400], episode='live')
        later = ev('later', DAYS[1550])
        catalog = CATALOG + [same, later]
        ids = {e.event_id for e in pr.comparables(catalog, LIVE)}
        self.assertNotIn('same-episode', ids)
        self.assertNotIn('later', ids)
        self.assertNotIn('live', ids)

    def test_idempotent(self):
        once = pr.record([], LIVE_DAY, [LIVE], comp, {'brent': CLOSES})
        later = nth_after(LIVE_DAY, 2)
        twice = pr.record(once, later, [LIVE], comp, {'brent': CLOSES})
        self.assertEqual(once, twice)    # not re-recorded with later numbers

    def test_known_outcome_not_recorded(self):
        late = nth_after(LIVE_DAY, 5)    # 5-day exit is published on this day
        rows = pr.record([], late, [LIVE], comp, {'brent': CLOSES})
        self.assertEqual([r.horizon for r in rows], [20, 60])

    def test_weekend_event_waits_for_monday(self):
        saturday = date(2020, 10, 3)
        self.assertEqual(saturday.weekday(), 5)
        weekend = ev('weekend', saturday)
        closes = {'brent': CLOSES}
        self.assertEqual(pr.record([], saturday, [weekend], comp, closes), [])
        self.assertEqual(pr.record([], saturday + timedelta(days=1), [weekend], comp, closes), [])
        rows = pr.record([], saturday + timedelta(days=2), [weekend], comp, closes)
        self.assertEqual({r.entry_date for r in rows}, {date(2020, 10, 5)})

    def test_no_entry_close_yet(self):
        closes = [c for c in CLOSES if c.on < LIVE_DAY]
        self.assertEqual(pr.record([], LIVE_DAY, [LIVE], comp, {'brent': closes}), [])

    def test_gap_beyond_study_limit_is_void(self):
        closes = [c for c in CLOSES if not LIVE_DAY <= c.on <= LIVE_DAY + timedelta(days=10)]
        today = LIVE_DAY + timedelta(days=12)
        rows = pr.record([], today, [LIVE], comp, {'brent': closes})
        self.assertTrue(rows)
        self.assertTrue(all(r.status == 'void' and r.entry_date is None for r in rows))

    def test_too_few_recorded_without_probability(self):
        few = PAST[:3] + [LIVE]
        rows = pr.record([], LIVE_DAY, [LIVE], lambda e: pr.comparables(few, e),
                         {'brent': CLOSES})
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r.p_rose is None and r.n == 3 for r in rows))
        scored = pr.score(rows, {'brent': CLOSES}, nth_after(LIVE_DAY, 60))
        self.assertTrue(all(r.status == 'scored' for r in scored))
        s = pr.summary(scored)
        self.assertEqual([(x.scored, x.with_p, x.brier_event, x.hits) for x in s],
                         [(1, 0, None, 0)] * 3)


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.rows = [r for r in pr.record([], LIVE_DAY, [LIVE], comp, {'brent': CLOSES})
                     if r.horizon == 5]

    def test_exactly_at_horizon(self):
        before = pr.score(self.rows, {'brent': CLOSES}, nth_after(LIVE_DAY, 4))
        self.assertEqual(before[0].status, 'open')
        at = nth_after(LIVE_DAY, 5)
        r = pr.score(self.rows, {'brent': CLOSES}, at)[0]
        self.assertEqual((r.status, r.exit_date, r.scored_on), ('scored', at, at))
        exit_close = CLOSES[DAYS.index(at)].value
        self.assertEqual(r.exit_close, exit_close)
        self.assertAlmostEqual(r.change, exit_close / r.entry_close - 1)
        self.assertEqual(r.rose, r.change > 0)

    def test_scored_row_never_changes(self):
        at = nth_after(LIVE_DAY, 5)
        scored = pr.score(self.rows, {'brent': CLOSES}, at)
        moved = [Close(c.on, c.value * 2) for c in CLOSES]
        self.assertEqual(pr.score(scored, {'brent': moved}, nth_after(LIVE_DAY, 30)), scored)

    def test_void_on_non_positive_exit(self):
        at = nth_after(LIVE_DAY, 5)
        bad = [Close(c.on, -1.0 if c.on == at else c.value) for c in CLOSES]
        r = pr.score(self.rows, {'brent': bad}, at)[0]
        self.assertEqual((r.status, r.change, r.rose), ('void', None, None))

    def test_void_on_non_positive_entry(self):
        bad = [Close(c.on, 0.0 if c.on == LIVE_DAY else c.value) for c in CLOSES]
        rows = pr.record([], LIVE_DAY, [LIVE], comp, {'wti': bad}, assets=('wti',))
        self.assertTrue(all(r.entry_close == 0.0 for r in rows))
        scored = pr.score(rows, {'wti': bad}, LIVE_DAY)
        self.assertTrue(all(r.status == 'void' for r in scored))
        self.assertEqual(pr.summary(scored), [])

    def test_summary_brier(self):
        rows = pr.score(pr.record([], LIVE_DAY, [LIVE], comp, {'brent': CLOSES}),
                        {'brent': CLOSES}, nth_after(LIVE_DAY, 60))
        for s, r in zip(pr.summary(rows), rows):
            y = 1.0 if r.rose else 0.0
            self.assertEqual((s.scored, s.with_p), (1, 1))
            self.assertAlmostEqual(s.brier_event, (r.p_rose - y) ** 2)
            self.assertAlmostEqual(s.brier_baseline, (r.baseline_p - y) ** 2)
            self.assertEqual(s.hits, int((r.p_rose >= 0.5) == r.rose))

    def test_csv_round_trip(self):
        rows = pr.score(pr.record([], LIVE_DAY, [LIVE], comp, {'brent': CLOSES}),
                        {'brent': CLOSES}, nth_after(LIVE_DAY, 20))
        self.assertEqual(pr.from_csv(pr.to_csv(rows)), rows)
        self.assertEqual(pr.from_csv(pr.to_csv([])), [])
        with self.assertRaises(ValueError):
            pr.from_csv(pr.to_csv(rows + rows[:1]))


class ScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        prices = self.dir / 'prices'
        prices.mkdir()
        (prices / 'brent.csv').write_text(
            'date,USD/barrel\n' + ''.join(f'{c.on.isoformat()},{c.value!r}\n' for c in CLOSES),
            encoding='utf-8')
        self.events = self.dir / 'events.csv'
        self.events.write_text(','.join(CATALOG_COLUMNS) + '\n' + ''.join(
            f'{e.event_id},{e.date_public.isoformat()},{e.title},{e.category},{e.region},'
            f'{e.episode},{e.source_url},yes,\n' for e in CATALOG), encoding='utf-8')
        self.log = self.dir / 'predictions' / 'log.csv'
        self.report = self.dir / 'reports' / 'prediction-log.md'

    def tearDown(self):
        self.tmp.cleanup()

    def run_on(self, today):
        # These tests simulate a live run on ``today`` (the real date is injected).
        return script.run(today, self.log, self.report, self.dir / 'prices', self.events,
                          now=today)

    def test_creates_log_with_header(self):
        script.read_log(self.log)
        self.assertEqual(self.log.read_text(encoding='utf-8').strip(), ','.join(pr.COLUMNS))

    def test_backfilled_today_uses_no_later_closes(self):
        rows, _ = self.run_on(LIVE_DAY)
        direct = pr.record([], LIVE_DAY, [LIVE], comp,
                           {'brent': [c for c in CLOSES if c.on <= LIVE_DAY]})
        self.assertEqual(rows, direct)
        self.assertTrue(all(r.status == 'open' for r in rows))
        # A later backfill scores only what was known by then.
        day = nth_after(LIVE_DAY, 20)
        rows, _ = self.run_on(day)
        self.assertEqual({r.horizon: r.status for r in rows}, {5: 'scored', 20: 'scored', 60: 'open'})
        self.assertTrue(all(r.exit_date <= day for r in rows if r.exit_date))

    def test_rerun_same_day_is_identical(self):
        self.run_on(LIVE_DAY)
        first = self.log.read_bytes()
        self.run_on(LIVE_DAY)
        self.assertEqual(self.log.read_bytes(), first)

    def test_atomic_write_keeps_old_file(self):
        self.run_on(LIVE_DAY)
        before = self.log.read_bytes()
        with mock.patch.object(script.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.run_on(nth_after(LIVE_DAY, 20))
        self.assertEqual(self.log.read_bytes(), before)
        self.assertEqual(sorted(os.listdir(self.log.parent)), ['log.csv'])

    def test_report_has_n_and_caveat(self):
        _, text = self.run_on(nth_after(LIVE_DAY, 3))
        self.assertIn('n=10', text)
        self.assertIn('95% CI', text)
        self.assertIn('range', text)
        self.assertIn('windows, 95% CI', text)
        self.assertIn('Not a forecast or advice', text)
        self.assertIn('Very few predictions', text)
        self.assertIn('## Open predictions', text)
        self.assertIn('## Scored so far', text)
        self.assertEqual(self.report.read_text(encoding='utf-8'), text)


if __name__ == '__main__':
    unittest.main()
