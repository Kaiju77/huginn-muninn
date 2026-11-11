import unittest
from datetime import date, timedelta

from src.huginn_muninn.study import (
    Close,
    Event,
    baseline_changes,
    event_return,
    format_result,
    run_study,
    sorted_closes,
    summarize,
    wilson_interval,
)


def weekdays(start, count):
    days, d = [], start
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def series(values, start=date(2020, 1, 1)):
    return [Close(d, float(v)) for d, v in zip(weekdays(start, len(values)), values)]


class WilsonTest(unittest.TestCase):
    def test_known_values(self):
        low, high = wilson_interval(5, 10)
        self.assertAlmostEqual(low, 0.2366, places=4)
        self.assertAlmostEqual(high, 0.7634, places=4)
        low, high = wilson_interval(0, 10)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 0.2775, places=4)
        low, high = wilson_interval(10, 10)
        self.assertAlmostEqual(low, 0.7225, places=4)
        self.assertEqual(high, 1.0)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            wilson_interval(1, 0)
        with self.assertRaises(ValueError):
            wilson_interval(11, 10)


class SummarizeTest(unittest.TestCase):
    def test_too_few_reports_no_share(self):
        s = summarize([0.1, -0.2, 0.3], min_n=8)
        self.assertTrue(s.too_few)
        self.assertIsNone(s.share)
        self.assertIsNone(s.ci_low)
        self.assertEqual((s.n, s.rises), (3, 2))
        self.assertAlmostEqual(s.median, 0.1)
        self.assertAlmostEqual(s.low, -0.2)
        self.assertAlmostEqual(s.high, 0.3)

    def test_zero_change_is_not_a_rise(self):
        s = summarize([0.0] * 8 + [0.01] * 2)
        self.assertEqual(s.rises, 2)
        self.assertAlmostEqual(s.share, 0.2)

    def test_empty(self):
        s = summarize([])
        self.assertEqual(s.n, 0)
        self.assertTrue(s.too_few)


class EventReturnTest(unittest.TestCase):
    def setUp(self):
        # 2020-01-01 is a Wednesday. Closes 100, 101, ..., 129 on weekdays.
        self.closes = sorted_closes(series(range(100, 130)))

    def test_entry_is_close_on_event_date(self):
        event = Event('e1', date(2020, 1, 1))
        result, reason = event_return(self.closes, event, 5)
        self.assertIsNone(reason)
        self.assertEqual(result.entry_date, date(2020, 1, 1))
        self.assertAlmostEqual(result.change, 105 / 100 - 1)

    def test_weekend_event_uses_previous_close_not_next(self):
        # Saturday 2020-01-04: last close before it is Friday 2020-01-03 (102).
        event = Event('e2', date(2020, 1, 4))
        result, _ = event_return(self.closes, event, 1)
        self.assertEqual(result.entry_date, date(2020, 1, 3))
        self.assertEqual(result.exit_date, date(2020, 1, 6))
        self.assertAlmostEqual(result.change, 103 / 102 - 1)

    def test_event_before_history_is_skipped(self):
        result, reason = event_return(self.closes, Event('e3', date(2019, 12, 1)), 5)
        self.assertIsNone(result)
        self.assertIn('no close', reason)

    def test_event_near_end_is_skipped_not_truncated(self):
        last = self.closes[-3].on
        result, reason = event_return(self.closes, Event('e4', last), 5)
        self.assertIsNone(result)
        self.assertIn('not enough', reason)


class BaselineTest(unittest.TestCase):
    def test_counts_every_window(self):
        closes = series([100, 110, 99, 120])
        changes = baseline_changes(closes, 1)
        self.assertEqual(len(changes), 3)
        self.assertEqual(sum(1 for c in changes if c > 0), 2)


class RunStudyTest(unittest.TestCase):
    def setUp(self):
        # Flat at 100, except a +10% jump the day after each event.
        values = [100.0] * 200
        self.events = []
        start = weekdays(date(2020, 1, 1), 200)
        for k, i in enumerate(range(10, 190, 18)):  # 10 events
            self.events.append(Event(f'e{k}', start[i]))
            for j in range(i + 1, 200):
                values[j] *= 1.10
        self.closes = series(values)

    def test_every_event_rises_and_baseline_is_lower(self):
        [result] = run_study(self.events, self.closes, horizons=(1,))
        self.assertEqual(result.events.n, 10)
        self.assertEqual(result.events.rises, 10)
        self.assertEqual(result.events.share, 1.0)
        self.assertAlmostEqual(result.events.median, 0.10)
        self.assertLess(result.baseline.share, 0.1)
        self.assertEqual(result.skipped, ())

    def test_era_filters_events_and_baseline(self):
        era = (date(2020, 1, 1), self.events[4].date_public)
        [result] = run_study(self.events, self.closes, horizons=(1,), era=era)
        self.assertEqual(result.events.n, 5)
        self.assertTrue(result.events.too_few)
        self.assertEqual(result.skipped, ())
        self.assertLess(result.baseline.n, len(self.closes) - 1)
        # Baseline windows start inside the era only.
        era_closes = [c for c in self.closes if c.on <= era[1]]
        self.assertEqual(result.baseline.n, len(era_closes))

    def test_duplicate_event_id_rejected(self):
        with self.assertRaises(ValueError):
            run_study([self.events[0], self.events[0]], self.closes)

    def test_duplicate_close_date_rejected(self):
        with self.assertRaises(ValueError):
            run_study(self.events, self.closes + [self.closes[0]])

    def test_format_has_n_ci_range_and_baseline(self):
        [result] = run_study(self.events, self.closes, horizons=(1,))
        line = format_result(result, 'Brent')
        self.assertIn('in 10 comparable events, Brent rose in 10 (100%', line)
        self.assertIn('95% CI', line)
        self.assertIn('range', line)
        self.assertIn('Baseline', line)

    def test_format_too_few_has_no_percentage_share(self):
        [result] = run_study(self.events[:3], self.closes, horizons=(1,))
        line = format_result(result, 'Brent')
        self.assertIn('too few comparable events (n=3', line)
        self.assertNotIn('CI', line)


if __name__ == '__main__':
    unittest.main()


class CodexReviewRegressionTest(unittest.TestCase):
    """One test per finding in the 2026-11-11 Codex review."""

    def test_1_era_baseline_drops_windows_starting_after_era_end(self):
        closes = series([0, 100, 200, 400, 800])
        changes = baseline_changes(closes, 1, last_start=closes[1].on)
        self.assertEqual(changes, [1.0])  # only the 100 -> 200 window

    def test_baseline_windows_do_not_overlap(self):
        closes = series([100, 101, 102, 103, 104, 105, 106])
        changes = baseline_changes(closes, 2)
        self.assertEqual(len(changes), 3)  # starts at 0, 2, 4
        self.assertAlmostEqual(changes[0], 102 / 100 - 1)
        self.assertAlmostEqual(changes[1], 104 / 102 - 1)

    def test_2_baseline_line_has_n_ci_and_range(self):
        events = [Event(f'e{i}', d.on) for i, d in enumerate(series(range(100, 120))[:8])]
        [result] = run_study(events, series(range(100, 120)), horizons=(1,))
        line = format_result(result, 'Brent')
        baseline = line[line.index('Baseline'):]
        self.assertIn('19 non-overlapping 1-day windows', baseline)
        self.assertIn('19 rose (100%, 95% CI', baseline)
        self.assertIn('range', baseline)

    def test_2_baseline_with_too_few_windows_shows_no_share(self):
        closes = series(range(100, 114))  # 14 closes: windows start at 0, 5
        events = [Event(f'e{i}', c.on) for i, c in enumerate(closes[:8])]
        [result] = run_study(events, closes, horizons=(5,))
        self.assertIn('Baseline: too few windows (n=2)', format_result(result))

    def test_3_min_n_below_eight_is_rejected(self):
        closes = series([100, 110])
        with self.assertRaises(ValueError):
            run_study([Event('e', closes[0].on)], closes, horizons=(1,), min_n=1)
        with self.assertRaises(ValueError):
            summarize([0.1], min_n=1)
        # Raising the bar is allowed.
        summarize([0.1] * 20, min_n=12)

    def test_4_bad_horizons_rejected_even_with_no_events(self):
        closes = series(range(100, 120))
        for bad in [(0,), (-1,), (), (1.5,), (True,)]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                run_study([], closes, horizons=bad)

    def test_empty_event_list_reports_no_comparable_events(self):
        [result] = run_study([], series(range(100, 140)), horizons=(1,))
        self.assertEqual(result.events.n, 0)
        self.assertIn('no comparable events', format_result(result))

    def test_5_non_finite_prices_are_rejected(self):
        for bad in (float('nan'), float('inf'), float('-inf')):
            closes = series([100, 101])
            closes[1] = Close(closes[1].on, bad)
            with self.assertRaises(ValueError, msg=repr(bad)):
                run_study([Event('e', closes[0].on)], closes, horizons=(1,))
        with self.assertRaises(ValueError):
            summarize([0.1] * 7 + [float('nan')])
