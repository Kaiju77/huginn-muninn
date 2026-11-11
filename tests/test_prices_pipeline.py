import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from scripts import event_study
from scripts.fetch_prices import (
    PAGE, eia_url, fetch_eia, fetch_norges, fetch_one, parse_eia, validate, write_csv,
)
from src.huginn_muninn.assets import ASSETS, BY_ID
from src.huginn_muninn.prices import load_closes
from src.huginn_muninn.study import Close, Event, event_path

ROOT = Path(__file__).resolve().parent.parent
BRENT, WTI, USD_NOK = BY_ID['brent'], BY_ID['wti'], BY_ID['usd_nok']


def payload(series, rows, total):
    return {'response': {'total': total, 'data': [
        {'period': d, 'series': series, 'value': v} for d, v in rows]}}


def weekdays(start, count):
    out, d = [], start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class AssetsTest(unittest.TestCase):
    def test_ids_unique_and_paths_under_data_prices(self):
        self.assertEqual(len({a.asset_id for a in ASSETS}), len(ASSETS))
        for a in ASSETS:
            self.assertEqual(a.csv_path.parent, ROOT / 'data' / 'prices')
            self.assertIn(a.source, ('eia', 'norges-bank'))


class EiaTest(unittest.TestCase):
    def test_url_uses_route_and_series(self):
        url = eia_url(WTI, 'K', 5000)
        self.assertIn('/v2/petroleum/pri/spt/data/?', url)
        self.assertIn('facets%5Bseries%5D%5B%5D=RWTC', url)
        self.assertIn('offset=5000', url)

    def test_parse_numbers_strings_and_nulls(self):
        rows = parse_eia(BRENT, payload('RBRTE', [('1987-05-20', '18.63'),
                                                  ('1987-05-21', 18.45),
                                                  ('1987-05-22', None)], 3))
        self.assertEqual(rows, [(date(1987, 5, 20), 18.63), (date(1987, 5, 21), 18.45)])

    def test_brent_rejects_non_positive_but_wti_keeps_april_2020(self):
        with self.assertRaises(ValueError):
            parse_eia(BRENT, payload('RBRTE', [('2020-04-20', '-1')], 1))
        rows = parse_eia(WTI, payload('RWTC', [('2020-04-20', '-36.98')], 1))
        self.assertEqual(rows, [(date(2020, 4, 20), -36.98)])
        for bad in ('nan', 'inf'):
            with self.assertRaises(ValueError):
                parse_eia(WTI, payload('RWTC', [('2020-04-20', bad)], 1))

    def test_wrong_series_or_shape_rejected(self):
        with self.assertRaises(ValueError):
            parse_eia(BRENT, payload('RWTC', [('2020-01-02', 1)], 1))
        with self.assertRaises(ValueError):
            parse_eia(BRENT, {'oops': 1})

    def test_paging(self):
        days = [d.isoformat() for d in weekdays(date(1987, 5, 20), PAGE + 10)]
        pages = {0: payload('RBRTE', [(d, 20) for d in days[:PAGE]], len(days)),
                 PAGE: payload('RBRTE', [(d, 21) for d in days[PAGE:]], len(days))}
        calls = []

        def fake_get(url):
            offset = int(url.split('offset=')[1].split('&')[0])
            calls.append(offset)
            return json.dumps(pages[offset]).encode()

        rows = fetch_eia(BRENT, 'k', fake_get)
        self.assertEqual(calls, [0, PAGE])
        self.assertEqual(len(rows), PAGE + 10)

    def test_missing_key_is_an_error_not_a_crash(self):
        with self.assertRaises(RuntimeError):
            fetch_one(BRENT, '', date(2026, 1, 1), get=lambda url: b'')


class NorgesBankTest(unittest.TestCase):
    def test_recorded_fixture_parses(self):
        body = (ROOT / 'fixtures' / 'http' / 'norges-bank-usd-nok.csv').read_bytes()
        rows = fetch_norges(USD_NOK, date(2026, 11, 1), get=lambda url: body)
        self.assertGreater(len(rows), 5)
        self.assertEqual(rows, sorted(rows))
        self.assertTrue(all(5 < price < 15 for _, price in rows))


class ValidateTest(unittest.TestCase):
    def test_rules(self):
        good = [(d, 20.0) for d in weekdays(date(1987, 5, 20), 2000)]
        validate(good, date(2100, 1, 1))
        with self.assertRaises(ValueError):
            validate(good[:10], date(2100, 1, 1))
        with self.assertRaises(ValueError):
            validate(good + [good[0]], date(2100, 1, 1))
        with self.assertRaises(ValueError):
            validate(good, date(1990, 1, 1))


class PathTest(unittest.TestCase):
    def test_event_path_after_and_before_news(self):
        days = weekdays(date(2020, 1, 1), 10)  # Wed 1 Jan ... closes 100..109
        closes = [Close(d, 100.0 + i) for i, d in enumerate(days)]
        path = event_path(closes, Event('e', date(2020, 1, 4)), days=3)  # Saturday
        self.assertEqual(path[0], (0, 0.0))
        self.assertEqual(len(path), 4)
        self.assertAlmostEqual(path[1][1], 104 / 103 - 1)  # entry Monday 103
        before = event_path(closes, Event('e', date(2020, 1, 4)), days=1, entry='before_news')
        self.assertAlmostEqual(before[1][1], 103 / 102 - 1)  # entry Friday 102

    def test_event_path_none_without_entry_and_short_at_end(self):
        closes = [Close(d, 50.0) for d in weekdays(date(2020, 1, 1), 5)]
        self.assertIsNone(event_path(closes, Event('e', date(2019, 1, 1))))
        path = event_path(closes, Event('e', date(2020, 1, 7)), days=60)
        self.assertEqual(len(path), 1)

    def test_event_path_skips_non_positive_entry(self):
        closes = [Close(date(2020, 4, 20), -36.98), Close(date(2020, 4, 21), 10.0)]
        self.assertIsNone(event_path(closes, Event('e', date(2020, 4, 20))))


class CliTest(unittest.TestCase):
    def test_cli_runs_every_asset_and_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            days = weekdays(date(1987, 5, 20), 10500)
            write_csv([(d, 20 + i * 0.001) for i, d in enumerate(days)], tmp / 'brent.csv',
                      'USD/barrel')
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = event_study.main(['--prices-dir', str(tmp)])
            text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn('21 events (28 in catalog)', text)
        self.assertIn('Brent (USD/barrel)', text)
        self.assertIn('20 trading days: in ', text)
        self.assertIn('WTI: no price file yet', text)
        self.assertIn('not a forecast or advice', text)


class PriceCsvStrictnessTest(unittest.TestCase):
    def test_bom_ok_and_wrong_width_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / 'g.csv'
            good.write_text('﻿date,usd_per_barrel\n2020-01-02,66.25\n', encoding='utf-8')
            self.assertEqual(len(load_closes(good)), 1)
            bad = Path(tmp) / 'b.csv'
            bad.write_text('date,usd_per_barrel\n2020-01-02,66.25,x\n')
            with self.assertRaises(ValueError):
                load_closes(bad)

    def test_real_brent_file_loads(self):
        closes = load_closes(ROOT / 'data' / 'prices' / 'brent.csv')
        self.assertGreater(len(closes), 10000)
        self.assertEqual(closes[0].on, date(1987, 5, 20))


if __name__ == '__main__':
    unittest.main()
