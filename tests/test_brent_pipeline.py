import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from scripts import event_study
from scripts.fetch_eia_brent import (
    PAGE, fetch_all, page_url, parse_rows, validate, write_csv,
)
from src.huginn_muninn.prices import load_closes


def payload(rows, total):
    return {'response': {'total': total, 'data': [
        {'period': d, 'series': 'RBRTE', 'value': v} for d, v in rows]}}


def weekdays(start, count):
    out, d = [], start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class FetchTest(unittest.TestCase):
    def test_url_has_series_and_paging_but_key_is_only_a_param(self):
        url = page_url('SECRET', 5000)
        self.assertIn('facets%5Bseries%5D%5B%5D=RBRTE', url)
        self.assertIn('offset=5000', url)

    def test_parse_accepts_numbers_and_strings_and_skips_nulls(self):
        rows = parse_rows(payload([('1987-05-20', '18.63'), ('1987-05-21', 18.45),
                                   ('1987-05-22', None)], 3))
        self.assertEqual(rows, [(date(1987, 5, 20), 18.63), (date(1987, 5, 21), 18.45)])

    def test_parse_rejects_bad_values(self):
        for bad in ('-1', '0', 'nan', 'inf'):
            with self.assertRaises(ValueError, msg=bad):
                parse_rows(payload([('2020-01-02', bad)], 1))
        with self.assertRaises(ValueError):
            parse_rows({'oops': 1})
        with self.assertRaises(ValueError):
            parse_rows({'response': {'data': [{'period': '2020-01-02', 'series': 'X', 'value': 1}]}})

    def test_fetch_pages_until_total(self):
        days = [d.isoformat() for d in weekdays(date(1987, 5, 20), PAGE + 10)]
        pages = {0: payload([(d, 20) for d in days[:PAGE]], len(days)),
                 PAGE: payload([(d, 21) for d in days[PAGE:]], len(days))}
        calls = []

        def fake_get(url):
            offset = int(url.split('offset=')[1].split('&')[0])
            calls.append(offset)
            return pages[offset]

        rows = fetch_all('k', get=fake_get)
        self.assertEqual(calls, [0, PAGE])
        self.assertEqual(len(rows), PAGE + 10)
        validate(rows, today=date(2100, 1, 1))

    def test_validate_rejects_short_unsorted_or_future(self):
        good = [(d, 20.0) for d in weekdays(date(1987, 5, 20), 2000)]
        with self.assertRaises(ValueError):
            validate(good[:10])
        with self.assertRaises(ValueError):
            validate(good + [good[0]], today=date(2100, 1, 1))
        with self.assertRaises(ValueError):
            validate(good, today=date(1990, 1, 1))


class PipelineTest(unittest.TestCase):
    def test_csv_round_trip_and_cli_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'brent.csv'
            days = weekdays(date(1987, 5, 20), 10500)
            write_csv([(d, 20 + i * 0.001) for i, d in enumerate(days)], out)
            closes = load_closes(out)
            self.assertEqual(len(closes), len(days))
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = event_study.main(['--prices', str(out)])
            text = buf.getvalue()
            self.assertEqual(code, 0)
            self.assertIn('Brent: 21 events (28 in catalog)', text)
            self.assertIn('20 trading days: in ', text)
            self.assertIn('not a forecast or advice', text)

    def test_bad_price_csv_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'b.csv'
            bad.write_text('date,usd_per_barrel\n2020-01-02,abc\n')
            with self.assertRaises(ValueError):
                load_closes(bad)


if __name__ == '__main__':
    unittest.main()


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
