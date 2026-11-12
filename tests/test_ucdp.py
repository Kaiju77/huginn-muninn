"""Tests for the UCDP GED fetcher and the rule-based onset catalog.

All GED data here is SYNTHETIC. The rows are shaped like the documented
UCDP API response (keys TotalCount, TotalPages, PreviousPageUrl,
NextPageUrl, Result; GED field names from the 26.1 codebook) but the
events, dates and death counts are made up.
"""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path

from scripts import build_ucdp_catalog, fetch_ucdp
from scripts.fetch_ucdp import (
    API_BASE, TOKEN_HEADER, fetch_ged, first_url, parse_page, read_ged_csv, validate, write_csv,
)
from src.huginn_muninn.catalog import first_per_episode, load_catalog
from src.huginn_muninn.ucdp_events import (
    CATEGORY, GedRow, OnsetRule, find_onsets, to_catalog_rows,
)

TODAY = date(2026, 11, 12)
SECRET = 'SYNTHETIC-SECRET-TOKEN-123'


def ged_item(i, day, country_id=645, country='Iraq', best=5, violence=1, prec=1,
             end=None):
    """One SYNTHETIC GED event, shaped like an API Result item."""
    return {
        'id': 900000 + i, 'relid': f'SYN-{i}', 'year': int(day[:4]), 'active_year': True,
        'code_status': 'Clear', 'type_of_violence': violence,
        'conflict_new_id': 1, 'conflict_name': 'SYNTHETIC conflict',
        'dyad_new_id': 1, 'dyad_name': 'SYNTHETIC dyad',
        'side_a': 'SYNTHETIC A', 'side_b': 'SYNTHETIC B',
        'number_of_sources': 1, 'source_article': 'synthetic',
        'where_prec': 1, 'where_coordinates': 'nowhere', 'adm_1': '', 'adm_2': '',
        'latitude': 33.0, 'longitude': 44.0, 'geom_wkt': 'POINT (44 33)',
        'priogrid_gid': 1, 'country': country, 'country_id': country_id,
        'region': 'Middle East', 'event_clarity': 1, 'date_prec': prec,
        'date_start': day + 'T00:00:00', 'date_end': (end or day) + 'T00:00:00',
        'deaths_a': 0, 'deaths_b': 0, 'deaths_civilians': best, 'deaths_unknown': 0,
        'best': best, 'high': best, 'low': best, 'gwnoa': '645', 'gwnob': '',
    }


def pages(items, size):
    """Split SYNTHETIC items into API-shaped pages linked by NextPageUrl."""
    chunks = [items[i:i + size] for i in range(0, len(items), size)] or [[]]
    out = {}
    for n, chunk in enumerate(chunks):
        url = API_BASE + f'26.1?pagesize={size}&page={n}'
        nxt = API_BASE + f'26.1?pagesize={size}&page={n + 1}' if n + 1 < len(chunks) else ''
        out[url] = {'TotalCount': len(items), 'TotalPages': len(chunks),
                    'PreviousPageUrl': '', 'NextPageUrl': nxt, 'Result': chunk}
    return out


class FakeGet:
    """Serves SYNTHETIC pages. The first request is the real first_url()."""

    def __init__(self, items, size):
        self.pages = pages(items, size)
        self.first = next(iter(self.pages))
        self.calls = []

    def __call__(self, url, token):
        self.calls.append((url, token))
        key = self.first if len(self.calls) == 1 else url
        return json.dumps(self.pages[key]).encode('utf-8')


def row(day, best, country_id=645, country='Iraq', violence=1, prec=1, end=None, i=0):
    d = date.fromisoformat(day)
    return GedRow(f'r{i}-{day}-{country_id}', d, date.fromisoformat(end) if end else d,
                  prec, country, country_id, 'Middle East', violence, best)


class ParseTest(unittest.TestCase):
    def test_parses_fixture_fields(self):
        payload = pages([ged_item(1, '2003-03-20', best=40)], 10)
        rows = parse_page(next(iter(payload.values())), TODAY)
        self.assertEqual(rows, [GedRow('900001', date(2003, 3, 20), date(2003, 3, 20), 1,
                                       'Iraq', 645, 'Middle East', 1, 40)])

    def test_string_numbers_accepted(self):
        item = ged_item(1, '2003-03-20')
        item.update(best='7', country_id='645', date_prec='1', type_of_violence='2')
        r = parse_page({'TotalCount': 1, 'TotalPages': 1, 'Result': [item]}, TODAY)[0]
        self.assertEqual((r.best, r.country_id, r.type_of_violence), (7, 645, 2))

    def test_first_url_has_version_pagesize_and_countries(self):
        url = first_url('26.1', 1000)
        self.assertTrue(url.startswith('https://ucdpapi.pcr.uu.se/api/gedevents/26.1?'))
        self.assertIn('pagesize=1000', url)
        self.assertIn('Country=620,630,645,652,660,663,666,670,678,680,690,692,694,696,698', url)

    def test_validation_failures(self):
        bad = [
            ('best', None), ('best', -1), ('best', 'many'), ('best', True),
            ('country_id', 2), ('type_of_violence', 4), ('date_prec', 9),
            ('date_start', 'yesterday'), ('date_end', None), ('id', ''), ('country', ''),
        ]
        for key, value in bad:
            item = ged_item(1, '2003-03-20')
            item[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                parse_page({'TotalCount': 1, 'TotalPages': 1, 'Result': [item]}, TODAY)

    def test_end_before_start_and_future_rejected(self):
        for item in (ged_item(1, '2003-03-20', end='2003-03-19'),
                     ged_item(1, '2026-11-13')):
            with self.assertRaises(ValueError):
                parse_page({'TotalCount': 1, 'TotalPages': 1, 'Result': [item]}, TODAY)

    def test_bad_shapes_rejected(self):
        for payload in ({}, {'Result': 'x', 'TotalCount': 0, 'TotalPages': 0},
                        {'Result': [], 'TotalPages': 0}, [1, 2]):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_page(payload, TODAY)


class PagingTest(unittest.TestCase):
    def items(self, n):
        return [ged_item(i, (date(2000, 1, 1) + timedelta(days=i)).isoformat())
                for i in range(n)]

    def test_follows_next_page_url_until_empty(self):
        get = FakeGet(self.items(25), 10)
        rows = fetch_ged('26.1', SECRET, TODAY, get, pagesize=10)
        self.assertEqual(len(rows), 25)
        self.assertEqual(len(get.calls), 3)
        self.assertTrue(all(token == SECRET for _, token in get.calls))
        self.assertTrue(all(SECRET not in url for url, _ in get.calls))

    def test_short_download_rejected(self):
        get = FakeGet(self.items(25), 10)
        for page in get.pages.values():
            page['TotalCount'] = 26
        with self.assertRaises(ValueError):
            fetch_ged('26.1', SECRET, TODAY, get, pagesize=10)

    def test_next_page_off_host_rejected(self):
        get = FakeGet(self.items(15), 10)
        get.pages[get.first]['NextPageUrl'] = 'https://evil.example/api/gedevents/26.1?page=1'
        with self.assertRaises(ValueError):
            fetch_ged('26.1', SECRET, TODAY, get, pagesize=10)

    def test_non_json_rejected(self):
        with self.assertRaises(ValueError):
            fetch_ged('26.1', SECRET, TODAY, lambda url, token: b'<html>', pagesize=10)

    def test_validate_min_rows_duplicates_and_shrink(self):
        rows = parse_page(pages(self.items(5), 10)[API_BASE + '26.1?pagesize=10&page=0'], TODAY)
        with self.assertRaises(ValueError):
            validate(rows, min_rows=6)
        with self.assertRaises(ValueError):
            validate(rows + rows[:1], min_rows=1)
        with self.assertRaises(ValueError):
            validate(rows, existing=[{}] * 10, min_rows=1)
        validate(rows, min_rows=5)


class MainTest(unittest.TestCase):
    def run_main(self, get, out, env_token=SECRET, argv=('--min-rows', '1')):
        old = fetch_ucdp.os.environ.get('UCDP_TOKEN')
        fetch_ucdp.os.environ['UCDP_TOKEN'] = env_token
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = fetch_ucdp.main(list(argv), get=get, out=out, today=TODAY)
        finally:
            if old is None:
                del fetch_ucdp.os.environ['UCDP_TOKEN']
            else:
                fetch_ucdp.os.environ['UCDP_TOKEN'] = old
        return code, stdout.getvalue() + stderr.getvalue()

    def test_writes_csv_and_never_prints_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'ged.csv'
            code, text = self.run_main(FakeGet([ged_item(1, '2003-03-20')], 10), out)
            self.assertEqual(code, 0)
            self.assertNotIn(SECRET, text)
            self.assertEqual(len(read_ged_csv(out)), 1)
            self.assertNotIn(SECRET, out.read_text())

    def test_failure_keeps_old_file_and_hides_token(self):
        def failing(url, token):
            raise RuntimeError(f'boom {token}')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'ged.csv'
            out.write_text('old\n')
            code, text = self.run_main(failing, out)
            self.assertEqual(code, 1)
            self.assertEqual(out.read_text(), 'old\n')
            self.assertNotIn(SECRET, text)
            self.assertIn('not written', text)

    def test_http_get_sends_token_as_header_only(self):
        captured = {}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{}'

        def fake_urlopen(request, timeout):
            captured['url'] = request.full_url
            captured['headers'] = {k.lower(): v for k, v in request.header_items()}
            return Resp()

        original = fetch_ucdp.urllib.request.urlopen
        fetch_ucdp.urllib.request.urlopen = fake_urlopen
        try:
            fetch_ucdp.http_get(first_url('26.1', 10), SECRET)
        finally:
            fetch_ucdp.urllib.request.urlopen = original
        self.assertEqual(captured['headers'][TOKEN_HEADER], SECRET)
        self.assertNotIn(SECRET, captured['url'])


class OnsetRuleTest(unittest.TestCase):
    def test_threshold_reached_on_exact_day(self):
        rows = [row('2000-06-01', 10, i=1), row('2000-06-03', 14, i=2),
                row('2000-06-05', 1, i=3)]
        onsets = find_onsets(rows)
        self.assertEqual([(o.day, o.window_deaths) for o in onsets],
                         [(date(2000, 6, 5), 25)])

    def test_below_threshold_no_event(self):
        self.assertEqual(find_onsets([row('2000-06-01', 24)]), [])

    def test_window_boundary(self):
        # 7-day window: day 1 and day 7 together, day 1 and day 8 not.
        inside = [row('2000-06-01', 13, i=1), row('2000-06-07', 12, i=2)]
        outside = [row('2000-06-01', 13, i=1), row('2000-06-08', 12, i=2)]
        self.assertEqual(len(find_onsets(inside)), 1)
        self.assertEqual(find_onsets(outside), [])

    def test_calm_gap_boundary(self):
        # Hot on 2000-06-01. Next burst exactly 90 days of window-sum later is
        # still inside the calm requirement only if any of the 90 prior days
        # was hot.
        first = row('2000-06-01', 30, i=1)
        last_hot = date(2000, 6, 7)  # window still >= 25 through 06-07
        too_soon = last_hot + timedelta(days=90)
        just_ok = last_hot + timedelta(days=91)
        self.assertEqual(len(find_onsets([first, row(too_soon.isoformat(), 30, i=2)])), 1)
        days = [o.day for o in find_onsets([first, row(just_ok.isoformat(), 30, i=2)])]
        self.assertEqual(days, [date(2000, 6, 1), just_ok])

    def test_sustained_violence_is_one_event(self):
        rows = [row((date(2001, 1, 1) + timedelta(days=i)).isoformat(), 10, i=i)
                for i in range(200)]
        self.assertEqual(len(find_onsets(rows)), 1)

    def test_calm_period_must_be_observed(self):
        early = [row('1989-02-01', 40)]
        self.assertEqual(find_onsets(early), [])
        self.assertEqual(len(find_onsets([row('1989-04-01', 40)])), 1)

    def test_multiple_countries_are_independent(self):
        rows = [row('2006-07-12', 30, 666, 'Israel', i=1),
                row('2006-07-13', 30, 660, 'Lebanon', i=2),
                row('2006-07-14', 10, 645, 'Iraq', i=3)]
        onsets = find_onsets(rows)
        self.assertEqual([o.country for o in onsets], ['Israel', 'Lebanon'])

    def test_type_and_precision_filters(self):
        self.assertEqual(find_onsets([row('2000-06-01', 30, violence=2)],
                                     OnsetRule(types=(1,))), [])
        self.assertEqual(find_onsets([row('2000-06-01', 30, prec=4)]), [])

    def test_anchor_date_end_by_default(self):
        r = row('2000-06-01', 30, prec=2, end='2000-06-05')
        self.assertEqual(find_onsets([r])[0].day, date(2000, 6, 5))
        self.assertEqual(find_onsets([r], OnsetRule(anchor='date_start'))[0].day,
                         date(2000, 6, 1))

    def test_bad_rule_rejected(self):
        for kwargs in ({'threshold': 0}, {'window_days': 0}, {'types': (4,)},
                       {'anchor': 'x'}, {'lag_days': -1}, {'calm_days': 0}):
            with self.subTest(**kwargs), self.assertRaises(ValueError):
                find_onsets([], OnsetRule(**kwargs))


class CatalogOutputTest(unittest.TestCase):
    def rows(self):
        return [row('2006-07-12', 30, 666, 'Israel', i=1),
                row('2006-07-13', 30, 660, 'Lebanon', i=2),
                row('2014-06-10', 100, 645, 'Iraq', i=3),
                row('2015-03-26', 50, 678, 'Yemen (North Yemen)', i=4)]

    def test_schema_ids_and_lag(self):
        out = to_catalog_rows(find_onsets(self.rows()), today=TODAY, version='26.1')
        first = out[0]
        self.assertEqual(first['event_id'], 'ucdp-2006-israel-0712')
        self.assertEqual(first['date_public'], '2006-07-13')
        self.assertEqual(first['category'], CATEGORY)
        self.assertEqual(first['region'], 'Israel')
        self.assertEqual(first['source_url'], 'https://ucdp.uu.se/country/666')
        self.assertEqual(first['source_checked'], 'yes')
        self.assertIn('30 deaths', first['notes'])
        self.assertIn('>=25', first['notes'])
        self.assertIn('GED 26.1', first['notes'])
        self.assertEqual(out[3]['event_id'], 'ucdp-2015-yemen-0326')

    def test_episode_merges_nearby_onsets_across_countries(self):
        out = to_catalog_rows(find_onsets(self.rows()), today=TODAY)
        self.assertEqual(out[0]['episode'], out[1]['episode'])
        self.assertNotEqual(out[1]['episode'], out[2]['episode'])
        self.assertEqual(len({r['episode'] for r in out}), 3)

    def test_no_future_dates(self):
        onsets = find_onsets([row('2026-11-12', 40)])
        self.assertEqual(to_catalog_rows(onsets, today=TODAY), [])
        self.assertEqual(len(to_catalog_rows(onsets, today=TODAY + timedelta(days=1))), 1)

    def test_load_catalog_accepts_output(self):
        out_rows = to_catalog_rows(find_onsets(self.rows()), today=TODAY)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mideast-conflict-ucdp.csv'
            with path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(out_rows[0]))
                writer.writeheader()
                writer.writerows(out_rows)
            events = load_catalog(path, category=CATEGORY, today=TODAY)
        self.assertEqual(len(events), 4)
        self.assertEqual(len(first_per_episode(events)), 3)
        self.assertTrue(all(e.date_public <= TODAY for e in events))


class BuildScriptTest(unittest.TestCase):
    def test_end_to_end_from_ged_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'ged.csv', Path(tmp) / 'events.csv'
            write_csv(CatalogOutputTest().rows(), src)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build_ucdp_catalog.main([], src=src, out=out, today=TODAY)
            self.assertEqual(code, 0)
            self.assertIn('4 onsets in 3 episodes', buf.getvalue())
            self.assertEqual(len(load_catalog(out, category=CATEGORY, today=TODAY)), 4)

    def test_missing_input_keeps_old_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'events.csv'
            out.write_text('old\n')
            with redirect_stderr(io.StringIO()):
                code = build_ucdp_catalog.main([], src=Path(tmp) / 'nope.csv', out=out,
                                               today=TODAY)
            self.assertEqual(code, 1)
            self.assertEqual(out.read_text(), 'old\n')

    def test_no_onsets_keeps_old_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'ged.csv', Path(tmp) / 'events.csv'
            write_csv([row('2000-06-01', 3)], src)
            out.write_text('old\n')
            with redirect_stderr(io.StringIO()):
                code = build_ucdp_catalog.main([], src=src, out=out, today=TODAY)
            self.assertEqual(code, 1)
            self.assertEqual(out.read_text(), 'old\n')


if __name__ == '__main__':
    unittest.main()
