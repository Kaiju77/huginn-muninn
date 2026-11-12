import unittest
from datetime import date, timedelta

from src.huginn_muninn.calibration import brier, score, walk_forward
from src.huginn_muninn.study import Close, Event


def weekdays(start, count):
    out, d = [], start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def rising_after_events(n_events=14, gap=30, days=600):
    """Flat prices that jump +10% the day after each event."""
    ds = weekdays(date(2000, 1, 3), days)
    values, events = [100.0] * days, []
    for k in range(n_events):
        i = 20 + k * gap
        events.append(Event(f'e{k}', ds[i]))
        for j in range(i + 1, days):
            values[j] *= 1.10
    return events, [Close(d, v) for d, v in zip(ds, values)]


class WalkForwardTest(unittest.TestCase):
    def test_only_outcomes_known_before_the_event_are_used(self):
        events, closes = rising_after_events()
        preds = walk_forward(events, closes, 1)
        # Event k can use events 0..k-1 (their 1-day exits are before it); needs 8.
        self.assertEqual([p.event_id for p in preds], [f'e{k}' for k in range(8, 14)])
        self.assertEqual([p.n for p in preds], list(range(8, 14)))
        self.assertTrue(all(p.p_event == 1.0 and p.rose for p in preds))

    def test_long_horizon_waits_for_exits(self):
        events, closes = rising_after_events(gap=10)
        preds = walk_forward(events, closes, 25)  # exits land after the next events
        for p in preds:
            k = int(p.event_id[1:])
            self.assertLess(p.n, k)  # fewer than all earlier events were known

    def test_baseline_uses_only_closes_before_the_event(self):
        events, closes = rising_after_events()
        first = walk_forward(events, closes, 1)[0]
        self.assertLess(first.p_baseline, 0.1)  # mostly flat days before e8


class ScoreTest(unittest.TestCase):
    def test_brier(self):
        self.assertAlmostEqual(brier([(1.0, True), (0.0, False)]), 0.0)
        self.assertAlmostEqual(brier([(0.5, True), (0.5, False)]), 0.25)
        self.assertIsNone(brier([]))
        self.assertIsNone(brier([(None, True)]))

    def test_perfect_model_beats_coin(self):
        events, closes = rising_after_events()
        s = score(walk_forward(events, closes, 1), 1)
        self.assertEqual((s.n, s.hits, s.rose), (6, 6, 6))
        self.assertAlmostEqual(s.brier_event, 0.0)
        self.assertAlmostEqual(s.brier_coin, 0.25)
        self.assertGreater(s.brier_baseline, s.brier_event)

    def test_empty(self):
        self.assertEqual(score([], 5).n, 0)


class ReportTest(unittest.TestCase):
    def test_backtest_report_on_real_data(self):
        from scripts.backtest import build
        text = build()
        self.assertIn('| Brent | 20 days |', text)
        self.assertIn('not a forecast or advice', text)


if __name__ == '__main__':
    unittest.main()
