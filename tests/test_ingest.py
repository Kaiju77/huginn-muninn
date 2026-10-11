import asyncio
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from src.huginn_muninn.evidence import open_evidence
from src.huginn_muninn.ingest.cache import read_desk_cache, write_refresh
from src.huginn_muninn.ingest.client import (
    ALLOWLIST,
    MAX_BODY_BYTES,
    MAX_RETRIES,
    MIN_INTERVAL_SECONDS,
    RETRY_STATUSES,
    STRUCTURED_ERRORS,
    TIMEOUT_SECONDS,
    Client,
    TransportResponse,
)
from src.huginn_muninn.ingest.ecb import CITATION, parse_nok_eur
from src.huginn_muninn.ingest.edgar import fetch_filings
from src.huginn_muninn.ingest.fred import HOSTS, status
from src.huginn_muninn.ingest.norges import (
    POLICY_RATE_KEY,
    POLICY_RATE_HTTP_STATUS,
    POLICY_RATE_SERIES,
    parse_exr,
    parse_nowa,
    parse_policy_rate,
    usd_nok_url,
)
from src.huginn_muninn.ingest.refresh import refresh_public
from src.huginn_muninn.ingest.ssb import CPI_URL, parse_cpi_total, parse_fixture
from src.huginn_muninn.prototype import dispatch, open_state


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'fixtures' / 'http'
STAMP = '2026-10-11T09:21:00+00:00'
WINDOW = ('2026-10-01', '2026-10-09')


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Script:
    def __init__(self, steps):
        self.steps = list(steps)
        self.urls = []

    def __call__(self, request):
        self.urls.append(request.url)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def _client(transport, cache, clock=None):
    if clock is None:
        clock = Clock()
    return Client(
        transport,
        cache,
        clock=clock,
        sleep=clock.sleep,
        retrieved_at=STAMP,
    )


def _response(status, body, origin='recorded'):
    if isinstance(body, str):
        body = body.encode('utf-8')
    return TransportResponse(status, body, origin)


class ClientContractTest(unittest.TestCase):
    def test_constants_and_allowlist(self):
        self.assertEqual(TIMEOUT_SECONDS, 15)
        self.assertEqual(MIN_INTERVAL_SECONDS, 2)
        self.assertEqual(MAX_RETRIES, 2)
        self.assertEqual(MAX_BODY_BYTES, 1000000)
        self.assertIn('body_too_large', STRUCTURED_ERRORS)
        self.assertEqual(
            STRUCTURED_ERRORS,
            frozenset((
                'not_allowlisted',
                'timeout',
                'http_status',
                'parse_error',
                'configuration_required',
                'body_too_large',
            )),
        )
        self.assertEqual(RETRY_STATUSES, frozenset((429, 500, 502, 503, 504)))
        self.assertEqual(
            ALLOWLIST,
            frozenset((
                'data.norges-bank.no',
                'data-api.ecb.europa.eu',
                'data.ssb.no',
                'data.sec.gov',
            )),
        )
        for host in HOSTS:
            self.assertNotIn(host, ALLOWLIST)
        self.assertEqual(status()['blocked_reason'], 'api_key_and_terms')
        self.assertIs(status()['live_fetch'], False)
        self.assertIs(status()['allowlisted'], False)

    def test_other_hosts_fail_before_the_transport(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        script = Script([])

        def explode(request):
            raise AssertionError(request.url)

        script = explode
        client = _client(script, Path(temporary.name))
        for url in (
            'https://api.stlouisfed.org/fred/series',
            'https://data.stlouisfed.org/fred/series',
            'https://example.com/rates',
            'http://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv',
        ):
            result = client.fetch(url)
            self.assertFalse(result.ok)
            self.assertEqual(result.reason, 'not_allowlisted')
            self.assertEqual(result.attempts, 0)
        self.assertEqual(list(Path(temporary.name).glob('**/*')), [])

    def test_timeout_retries_twice_and_other_4xx_do_not(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        clock = Clock()
        script = Script([TimeoutError('timed out'), TimeoutError('timed out'), TimeoutError('timed out')])
        client = _client(script, Path(temporary.name), clock)
        url = usd_nok_url(*WINDOW)
        result = client.fetch(url)
        self.assertEqual(result.reason, 'timeout')
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(script.urls), 3)
        self.assertEqual(clock.sleeps, [2.0, 2.0])
        for status_code in (400, 404):
            clock = Clock()
            script = Script([_response(status_code, b'no')])
            client = _client(script, Path(temporary.name), clock)
            result = client.fetch(url)
            self.assertEqual(result.reason, 'http_status')
            self.assertEqual(result.status, status_code)
            self.assertEqual(result.attempts, 1)
            self.assertEqual(clock.sleeps, [])
            self.assertEqual(script.steps, [])

    def test_retryable_statuses_stop_after_two_retries(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        url = usd_nok_url(*WINDOW)
        clock = Clock()
        script = Script([_response(429, b'later'), _response(200, b'ok')])
        client = _client(script, Path(temporary.name), clock)
        result = client.fetch(url)
        self.assertTrue(result.ok)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.body, b'ok')
        self.assertEqual(clock.sleeps, [2.0])
        clock = Clock()
        script = Script([
            _response(503, b'a'),
            _response(503, b'b'),
            _response(503, b'c'),
        ])
        client = _client(script, Path(temporary.name), clock)
        result = client.fetch(url)
        self.assertEqual(result.reason, 'http_status')
        self.assertEqual(result.status, 503)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(clock.sleeps, [2.0, 2.0])

    def test_same_host_waits_and_another_host_does_not(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        clock = Clock()
        script = Script([
            _response(200, b'one'),
            _response(200, b'two'),
            _response(200, b'three'),
        ])
        client = _client(script, Path(temporary.name), clock)
        first = usd_nok_url(*WINDOW)
        second = 'https://data-api.ecb.europa.eu/service/data/EXR/D.NOK.EUR.SP00.A?format=csvdata'
        self.assertTrue(client.fetch(first).ok)
        self.assertTrue(client.fetch(second).ok)
        self.assertEqual(clock.sleeps, [])
        self.assertTrue(client.fetch(first).ok)
        self.assertEqual(clock.sleeps, [2.0])

    def test_cache_stores_body_url_status_and_timestamp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        cache = Path(temporary.name)
        body = b'FREQ;TIME_PERIOD;OBS_VALUE\n'
        script = Script([_response(200, body)])
        client = _client(script, cache, Clock())
        url = usd_nok_url(*WINDOW)
        result = client.fetch(url)
        self.assertTrue(result.ok)
        self.assertEqual(result.retrieved_at, STAMP)
        entries = list((cache / 'entries').glob('*.json'))
        self.assertEqual(len(entries), 1)
        stored = json.loads(entries[0].read_text(encoding='utf-8'))
        self.assertEqual(stored['url'], url)
        self.assertEqual(stored['status'], 200)
        self.assertEqual(stored['retrieved_at'], STAMP)
        raw = (cache / stored['body_file']).read_bytes()
        self.assertEqual(raw, body)

    def test_async_fetch_and_the_sync_wrapper_return_the_body(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        cache = Path(temporary.name)
        url = usd_nok_url(*WINDOW)
        sync_client = _client(Script([_response(200, b'sync')]), cache, Clock())
        async_client = _client(Script([_response(200, b'async')]), cache, Clock())
        sync_result = sync_client.fetch(url)
        async_result = asyncio.run(async_client.fetch_async(url))
        self.assertEqual(sync_result.body, b'sync')
        self.assertEqual(async_result.body, b'async')
        self.assertTrue(sync_result.ok)
        self.assertTrue(async_result.ok)

    def test_a_body_larger_than_one_million_bytes_is_rejected_before_parsing(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        url = usd_nok_url(*WINDOW)
        accepted = _client(
            Script([_response(200, b'a' * MAX_BODY_BYTES)]),
            Path(temporary.name),
            Clock(),
        )
        within = accepted.fetch(url)
        self.assertTrue(within.ok)
        self.assertNotEqual(within.reason, 'body_too_large')
        rejected = _client(
            Script([_response(200, b'a' * (MAX_BODY_BYTES + 1))]),
            Path(temporary.name),
            Clock(),
        )
        result = rejected.fetch(url)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, 'body_too_large')
        self.assertEqual(result.attempts, 1)
        self.assertEqual(len(result.body), MAX_BODY_BYTES + 1)


class AdapterContractTest(unittest.TestCase):
    def test_norges_bank_fixture_parses_without_relabeling_the_collection(self):
        path = FIXTURES / 'norges-bank-usd-nok.csv'
        text = path.read_text(encoding='utf-8')
        self.assertEqual(
            text.splitlines()[0],
            'FREQ;Frequency;BASE_CUR;Base Currency;QUOTE_CUR;Quote Currency;TENOR;Tenor;'
            'DECIMALS;CALCULATED;UNIT_MULT;Unit Multiplier;COLLECTION;Collection Indicator;'
            'TIME_PERIOD;OBS_VALUE',
        )
        self.assertIn('ECB concertation time 14:15 CET', text)
        self.assertNotIn('2026-10-03', text)
        self.assertNotIn('2026-10-04', text)
        url = usd_nok_url(*WINDOW)
        parsed = parse_exr(text, url, '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        rows = parsed.observations
        self.assertEqual(
            [row['observation_time'] for row in rows],
            [
                '2026-10-01',
                '2026-10-02',
                '2026-10-05',
                '2026-10-06',
                '2026-10-07',
                '2026-10-08',
                '2026-10-09',
            ],
        )
        self.assertEqual(
            [row['value'] for row in rows],
            ['9.6256', '9.6494', '9.6015', '9.5643', '9.584', '9.5807', '9.5623'],
        )
        last = rows[-1]
        self.assertEqual(last['observation_id'], 'nb-exr-USD-NOK-2026-10-09')
        self.assertEqual(last['source_id'], 'norges-bank-open-data')
        self.assertEqual(last['subject'], 'USD/NOK')
        self.assertEqual(last['unit'], 'NOK per 1 USD')
        self.assertEqual(last['value'], '9.5623')
        self.assertEqual(Decimal(last['value']), Decimal('9.5623'))
        self.assertEqual(last['quality'], ['recorded_fixture'])
        self.assertIn('Norges Bank open data', last['provenance'])
        self.assertIn(url, last['provenance'])
        self.assertNotIn('ECB concertation', last['provenance'])
        self.assertNotIn(CITATION, last['provenance'])
        live = parse_exr(text, url, '2026-10-11', 'live')
        self.assertEqual(live.observations[0]['quality'], ['live_retrieval'])
        broken = parse_exr(b'nope', url, '2026-10-11', 'recorded')
        self.assertEqual(broken.error.reason, 'parse_error')
        self.assertEqual(broken.observations, ())

    def test_eur_nok_uses_the_same_parser_when_a_body_is_supplied(self):
        body = (
            'FREQ;Frequency;BASE_CUR;Base Currency;QUOTE_CUR;Quote Currency;TENOR;Tenor;'
            'DECIMALS;CALCULATED;UNIT_MULT;Unit Multiplier;COLLECTION;Collection Indicator;'
            'TIME_PERIOD;OBS_VALUE\n'
            'B;Business;EUR;Euro;NOK;Norwegian krone;SP;Spot;4;false;0;Units;C;'
            'ECB concertation time 14:15 CET;2026-10-09;11.0001\n'
        )
        parsed = parse_exr(body, 'https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=csv', '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        row = parsed.observations[0]
        self.assertEqual(row['observation_id'], 'nb-exr-EUR-NOK-2026-10-09')
        self.assertEqual(row['unit'], 'NOK per 1 EUR')
        self.assertEqual(row['value'], '11.0001')
        self.assertNotIn('ECB concertation', row['provenance'])
        self.assertEqual(POLICY_RATE_KEY, 'IR/K.POL.NOK')
        self.assertEqual(POLICY_RATE_HTTP_STATUS, 404)
        self.assertEqual(POLICY_RATE_SERIES, 'IR/B.KPRA.SD.R')

    def test_captured_eur_nok_fixture_stays_a_norges_bank_series(self):
        path = FIXTURES / 'norges-bank-eur-nok.csv'
        text = path.read_text(encoding='utf-8')
        usd_header = (FIXTURES / 'norges-bank-usd-nok.csv').read_text(encoding='utf-8').splitlines()[0]
        self.assertEqual(text.splitlines()[0], usd_header)
        self.assertEqual(
            [line.split(';')[-2:] for line in text.splitlines()[1:]],
            [['2026-10-08', '10.717'], ['2026-10-09', '10.7155']],
        )
        url = 'https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=csv&startPeriod=2026-10-08&endPeriod=2026-10-09'
        parsed = parse_exr(text, url, '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        self.assertEqual(
            [(row['observation_id'], row['value'], row['unit']) for row in parsed.observations],
            [
                ('nb-exr-EUR-NOK-2026-10-08', '10.717', 'NOK per 1 EUR'),
                ('nb-exr-EUR-NOK-2026-10-09', '10.7155', 'NOK per 1 EUR'),
            ],
        )
        last = parsed.observations[-1]
        self.assertEqual(last['source_id'], 'norges-bank-open-data')
        self.assertEqual(last['subject'], 'EUR/NOK')
        self.assertIn('Norges Bank open data', last['provenance'])
        self.assertIn(url, last['provenance'])
        self.assertNotIn(CITATION, last['provenance'])
        self.assertNotIn('ECB concertation', last['provenance'])

    def test_policy_rate_fixture_keeps_the_value_text_and_rejects_another_tenor(self):
        path = FIXTURES / 'norges-bank-policy-rate.csv'
        text = path.read_text(encoding='utf-8')
        self.assertIn('4.5', text)
        self.assertNotIn('4.50', text)
        self.assertNotIn(POLICY_RATE_KEY, text)
        url = 'https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R?format=csv&startPeriod=2026-10-06&endPeriod=2026-10-08'
        parsed = parse_policy_rate(text, url, '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        self.assertEqual(
            [(row['observation_id'], row['value']) for row in parsed.observations],
            [
                ('nb-ir-KPRA-SD-2026-10-06', '4.5'),
                ('nb-ir-KPRA-SD-2026-10-07', '4.5'),
                ('nb-ir-KPRA-SD-2026-10-08', '4.5'),
            ],
        )
        last = parsed.observations[-1]
        self.assertEqual(last['subject'], 'policy-rate')
        self.assertEqual(last['unit'], 'percent')
        self.assertEqual(last['value'], '4.5')
        self.assertIn('Norges Bank open data', last['provenance'])
        self.assertIn(url, last['provenance'])
        self.assertNotIn(CITATION, last['provenance'])
        lines = text.splitlines()
        mixed = '\n'.join((
            lines[0],
            lines[1],
            'B;Business;KPRA;Key policy rate;OL;Overnight lending;R;Rate;2;E;End of day;2026-10-07;5.0;;',
        ))
        rejected = parse_policy_rate(mixed, url, '2026-10-11', 'recorded')
        self.assertEqual(rejected.observations, ())
        self.assertEqual(rejected.error.reason, 'parse_error')

    def test_nowa_fixture_stores_the_rate_and_skips_other_rows(self):
        path = FIXTURES / 'norges-bank-nowa.csv'
        text = path.read_text(encoding='utf-8')
        url = 'https://data.norges-bank.no/api/data/SHORT_RATES/B.NOWA.ON.R?format=csv'
        parsed = parse_nowa(text, url, '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        self.assertEqual(
            [(row['observation_id'], row['value']) for row in parsed.observations],
            [
                ('nb-short-NOWA-ON-R-2026-10-06', '4.50'),
                ('nb-short-NOWA-ON-R-2026-10-07', '4.50'),
                ('nb-short-NOWA-ON-R-2026-10-08', '4.50'),
            ],
        )
        last = parsed.observations[-1]
        self.assertEqual(last['subject'], 'nowa')
        self.assertEqual(last['unit'], 'percent')
        self.assertEqual(last['value'], '4.50')
        self.assertIn('Norges Bank open data', last['provenance'])
        self.assertIn(url, last['provenance'])
        header = text.splitlines()[0]
        mixed = '\n'.join((
            header,
            'B;Business;NOWA;NOWA;ON;Overnight;VOL;Volume;;2;2026-10-06;100;N;Normal',
            'B;Business;NOWA;NOWA;IDX;Index;R;Rate;;2;2026-10-06;9;N;Normal',
            'B;Business;NOWA;NOWA;ON;Overnight;R;Rate;;2;2026-10-06;4.50;N;Normal',
        ))
        selected = parse_nowa(mixed, url, '2026-10-11', 'recorded')
        self.assertIsNone(selected.error)
        self.assertEqual(len(selected.observations), 1)
        self.assertEqual(selected.observations[0]['value'], '4.50')
        self.assertEqual(selected.observations[0]['observation_id'], 'nb-short-NOWA-ON-R-2026-10-06')

    def test_ecb_fixture_keeps_the_observation_text_and_the_citation(self):
        text = (FIXTURES / 'ecb-nok-eur.csv').read_text(encoding='utf-8')
        url = (
            'https://data-api.ecb.europa.eu/service/data/EXR/D.NOK.EUR.SP00.A'
            '?format=csvdata&startPeriod=2026-10-08&endPeriod=2026-10-09'
        )
        parsed = parse_nok_eur(text, url, '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        self.assertEqual(
            [(row['observation_time'], row['value']) for row in parsed.observations],
            [('2026-10-08', '10.717'), ('2026-10-09', '10.7155')],
        )
        last = parsed.observations[-1]
        self.assertEqual(last['observation_id'], 'ecb-exr-NOK-EUR-2026-10-09')
        self.assertEqual(last['unit'], 'NOK per 1 EUR')
        self.assertEqual(last['value'], '10.7155')
        self.assertIn(CITATION, last['provenance'])
        self.assertEqual(last['quality'], ['recorded_fixture'])
        self.assertEqual(Decimal(last['value']), Decimal('10.7155'))
        earlier = parsed.observations[0]
        self.assertEqual(earlier['value'], '10.717')
        self.assertEqual(Decimal(earlier['value']), Decimal('10.717'))

    def test_statistics_norway_parses_one_recorded_row(self):
        body = (FIXTURES / 'ssb-one-row.json').read_text(encoding='utf-8')
        parsed = parse_fixture(body, '2026-10-11')
        self.assertIsNone(parsed.error)
        self.assertEqual(len(parsed.observations), 1)
        row = parsed.observations[0]
        self.assertEqual(row['source_id'], 'ssb-statbank')
        self.assertEqual(row['value'], '1')
        self.assertEqual(row['quality'], ['recorded_fixture'])
        self.assertIn('CC BY 4.0', row['provenance'])
        self.assertIn('not security prices', row['provenance'])

    def test_cpi_cell_keeps_the_value_text_and_rejects_a_longer_list(self):
        path = FIXTURES / 'ssb-cpi-total-2026m07.json'
        text = path.read_text(encoding='utf-8')
        self.assertEqual(path.stat().st_size, 3303)
        self.assertIn('[103.8]', text)
        self.assertNotIn('"103.8"', text)
        parsed = parse_cpi_total(text, CPI_URL, '2026-10-11', 'recorded')
        self.assertIsNone(parsed.error)
        self.assertEqual(len(parsed.observations), 1)
        row = parsed.observations[0]
        self.assertIsInstance(row['value'], str)
        self.assertEqual(row['value'], '103.8')
        self.assertEqual(row['observation_id'], 'ssb-cpi-total-2026M07')
        self.assertEqual(row['source_id'], 'ssb-statbank')
        self.assertEqual(row['subject'], 'cpi-total')
        self.assertEqual(row['unit'], 'index 2025=100')
        self.assertEqual(row['observation_time'], '2026-07-01')
        self.assertEqual(row['quality'], ['recorded_fixture'])
        self.assertIn('Statistics Norway', row['provenance'])
        self.assertIn('CC BY 4.0', row['provenance'])
        self.assertIn('14700', row['provenance'])
        self.assertIn('price index', row['provenance'])
        self.assertIn('not a security price', row['provenance'])
        self.assertNotIn('@', row['provenance'])
        self.assertEqual(Decimal(row['value']), Decimal('103.8'))
        document = json.loads(text, parse_float=str)
        self.assertEqual(document['value'], ['103.8'])
        document['value'].append('104.0')
        rejected = parse_cpi_total(json.dumps(document), CPI_URL, '2026-10-11', 'recorded')
        self.assertEqual(rejected.observations, ())
        self.assertEqual(rejected.error.reason, 'parse_error')
        source = (ROOT / 'src' / 'huginn_muninn' / 'ingest' / 'ssb.py').read_text(encoding='utf-8')
        self.assertIn('parse_float=str', source)
        self.assertEqual(source.count('https://data.ssb.no'), 1)
        self.assertIn(CPI_URL, source)
        self.assertNotIn('add_rate', source)
        self.assertNotIn('ledger', source)

    def test_edgar_refuses_without_a_contact_string(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        def explode(request):
            raise AssertionError(request.url)

        client = _client(explode, Path(temporary.name), Clock())
        result = asyncio.run(fetch_filings(client, '', 'https://data.sec.gov/submissions/sample.json'))
        self.assertEqual(result.observations, ())
        self.assertEqual(result.error.reason, 'configuration_required')
        blank = asyncio.run(fetch_filings(client, '   ', 'https://data.sec.gov/submissions/sample.json'))
        self.assertEqual(blank.error.reason, 'configuration_required')

    def test_ingest_package_does_not_touch_the_ledger(self):
        package = ROOT / 'src' / 'huginn_muninn' / 'ingest'
        for path in package.glob('*.py'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('add_rate', text)
            self.assertNotIn('ledger', text)
        evidence = (ROOT / 'src' / 'huginn_muninn' / 'evidence.py').read_text(encoding='utf-8')
        self.assertNotIn('urllib', evidence)


class RefreshDeskTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self._tmp.name) / 'ingest-cache'
        self.overlay = Path(self._tmp.name) / 'synthetic-book.json'
        self.state = open_state(ROOT, self.overlay)
        self.state.ingest_cache_dir = self.cache
        import urllib.request
        self._opener = urllib.request.build_opener
        self._urlopen = urllib.request.urlopen

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked

    def tearDown(self):
        import urllib.request
        urllib.request.build_opener = self._opener
        urllib.request.urlopen = self._urlopen
        self._tmp.cleanup()

    def _transport(self, ecb_status=200):
        bodies = {
            'EXR/B.USD.NOK.SP': (FIXTURES / 'norges-bank-usd-nok.csv').read_bytes(),
            'EXR/B.EUR.NOK.SP': (FIXTURES / 'norges-bank-eur-nok.csv').read_bytes(),
            'IR/B.KPRA.SD.R': (FIXTURES / 'norges-bank-policy-rate.csv').read_bytes(),
            'SHORT_RATES/B.NOWA.ON.R': (FIXTURES / 'norges-bank-nowa.csv').read_bytes(),
        }
        ecb = (FIXTURES / 'ecb-nok-eur.csv').read_bytes()
        cpi = (FIXTURES / 'ssb-cpi-total-2026m07.json').read_bytes()

        class Transport:
            def __init__(self):
                self.urls = []

            def __call__(self, request):
                self.urls.append(request.url)
                host = urlsplit(request.url).hostname
                path = urlsplit(request.url).path
                if host == 'data.norges-bank.no':
                    for key, body in bodies.items():
                        if key in path:
                            return TransportResponse(200, body, 'recorded')
                    raise AssertionError(request.url)
                if host == 'data-api.ecb.europa.eu':
                    body = ecb if ecb_status == 200 else b'missing'
                    return TransportResponse(ecb_status, body, 'recorded')
                if request.url == CPI_URL:
                    return TransportResponse(200, cpi, 'recorded')
                raise AssertionError(request.url)

        return Transport()

    def test_fake_transport_keeps_the_synthetic_ledger_rate(self):
        transport = self._transport()
        clock = Clock()
        self.state.ingest_transport = transport
        before_value = self.state.ledger.value('2026-03-31')
        before_books = self.state.ledger.books('2026-03-31')
        self.assertTrue(before_value.complete)
        self.assertEqual(before_value.known_subtotal, Decimal('24932.50'))
        result = refresh_public(
            self.cache,
            *WINDOW,
            transport=transport,
            retrieved_at=STAMP,
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertEqual(result.errors, ())
        self.assertEqual(clock.sleeps, [2.0, 2.0, 2.0])
        self.assertEqual(len(transport.urls), 6)
        self.assertIn('/api/data/EXR/B.USD.NOK.SP?', transport.urls[0])
        self.assertIn('/api/data/EXR/B.EUR.NOK.SP?', transport.urls[1])
        self.assertIn('/api/data/IR/B.KPRA.SD.R?', transport.urls[2])
        self.assertIn('/api/data/SHORT_RATES/B.NOWA.ON.R?', transport.urls[3])
        self.assertIn('/service/data/EXR/D.NOK.EUR.SP00.A?', transport.urls[4])
        joined = '\n'.join(transport.urls)
        self.assertIn('startPeriod=2026-10-01', joined)
        self.assertIn('endPeriod=2026-10-09', joined)
        self.assertIn('EXR/B.USD.NOK.SP', joined)
        self.assertIn('EXR/D.NOK.EUR.SP00.A', joined)
        self.assertNotIn(POLICY_RATE_KEY, joined)
        self.assertIn('EXR/B.EUR.NOK.SP', joined)
        self.assertIn(POLICY_RATE_SERIES, joined)
        self.assertIn('SHORT_RATES/B.NOWA.ON.R', joined)
        self.assertEqual(transport.urls[5], CPI_URL)
        self.assertEqual([url for url in transport.urls if 'data.ssb.no' in url], [CPI_URL])
        self.assertNotIn('03013', joined)
        self.assertNotIn('data.sec.gov', joined)
        self.assertNotIn('stlouisfed.org', joined)
        values = [row['value'] for row in result.observations]
        self.assertIn('4.5', values)
        self.assertIn('9.5623', values)
        self.assertEqual(self.state.ledger.value('2026-03-31'), before_value)
        self.assertIn('9.584', values)
        self.assertIn('10.717', values)
        self.assertIn('10.7155', values)
        self.assertIn('4.50', values)
        self.assertIn('103.8', values)
        cpi_rows = [
            row for row in result.observations
            if row['observation_id'] == 'ssb-cpi-total-2026M07'
        ]
        self.assertEqual(len(cpi_rows), 1)
        self.assertIsInstance(cpi_rows[0]['value'], str)
        self.assertEqual(cpi_rows[0]['value'], '103.8')
        self.assertEqual(cpi_rows[0]['subject'], 'cpi-total')
        self.assertEqual(cpi_rows[0]['unit'], 'index 2025=100')
        self.assertEqual(cpi_rows[0]['observation_time'], '2026-07-01')
        self.assertIn('not a security price', cpi_rows[0]['provenance'])
        nok = [row for row in result.observations if row['observation_id'] == 'nb-exr-USD-NOK-2026-10-09']
        self.assertEqual(nok[0]['quality'], ['recorded_fixture'])
        ecb_last = [
            row for row in result.observations
            if row['observation_id'] == 'ecb-exr-NOK-EUR-2026-10-09'
        ]
        self.assertEqual(len(ecb_last), 1)
        self.assertIn(CITATION, ecb_last[0]['provenance'])
        store = open_evidence(ROOT)
        for row in result.observations:
            self.assertTrue(store.ingest(row).stored)
        stored = {
            item.observation_id: item
            for item in store.observations()
        }
        self.assertEqual(stored['nb-exr-USD-NOK-2026-10-09'].value, Decimal('9.5623'))
        self.assertEqual(stored['ecb-exr-NOK-EUR-2026-10-08'].value, Decimal('10.717'))
        self.assertEqual(stored['ssb-cpi-total-2026M07'].value, Decimal('103.8'))
        booked = self.state.ledger.value('2026-03-31')
        self.assertEqual(booked, before_value)
        self.assertTrue(booked.complete)
        self.assertEqual(booked.known_subtotal, Decimal('24932.50'))
        response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertEqual(response.status, 200)
        body = response.body
        svg = body.split('id="usd-nok-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertIn('data-date="2026-10-09"', svg)
        self.assertIn('data-value="9.5623"', svg)
        self.assertIn('data-kind="recorded"', svg)
        self.assertIn('>recorded<', svg)
        self.assertNotIn('>live<', svg)
        self.assertNotIn('data-date="2026-10-03"', svg)
        self.assertNotIn('data-date="2026-10-04"', svg)
        self.assertIn('data-segment="2026-10-01/2026-10-02"', svg)
        self.assertNotIn('data-segment="2026-10-02/2026-10-05"', svg)
        self.assertNotIn('10.25', svg)
        self.assertNotIn('2026-03-31', svg)
        self.assertNotIn('data-value="4.5"', svg)
        self.assertNotIn('data-value="4.50"', svg)
        policy = body.split('id="policy-rate-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertIn('data-value="4.5"', policy)
        self.assertIn('data-kind="recorded"', policy)
        self.assertIn('data-date="2026-10-08"', policy)
        self.assertIn('data-segment="2026-10-06/2026-10-07"', policy)
        self.assertIn('data-segment="2026-10-07/2026-10-08"', policy)
        self.assertNotIn('data-value="4.50"', policy)
        self.assertNotIn('data-date="2026-01-02"', policy)
        self.assertNotIn('>live<', policy)
        nowa = body.split('id="nowa-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertIn('data-value="4.50"', nowa)
        self.assertIn('data-kind="recorded"', nowa)
        self.assertIn('data-date="2026-10-06"', nowa)
        self.assertIn('data-date="2026-10-07"', nowa)
        self.assertIn('data-date="2026-10-08"', nowa)
        self.assertIn('data-segment="2026-10-06/2026-10-07"', nowa)
        self.assertIn('data-segment="2026-10-07/2026-10-08"', nowa)
        self.assertNotIn('data-date="2026-01-02"', nowa)
        self.assertNotIn('data-value="4.5"', nowa.replace('data-value="4.50"', ''))
        self.assertNotIn('data-value="9.5623"', nowa)
        self.assertNotIn('data-value="10.717"', nowa)
        self.assertNotIn('data-value="10.7155"', nowa)
        self.assertNotIn('10.25', nowa)
        self.assertNotIn('2026-03-31', nowa)
        self.assertNotIn('103.8', nowa)
        for day, amount in (('2026-10-08', '10.717'), ('2026-10-09', '10.7155')):
            pair = body.split(f'data-eur-nok-pair="{day}"', 1)[1].split('</p>', 1)[0]
            self.assertIn(f'data-norges-bank="{amount}"', pair)
            self.assertIn(f'data-ecb="{amount}"', pair)
            self.assertIn('data-difference="0"', pair)
            self.assertIn(
                'This difference is not a recommendation and is not copied into the ledger.',
                pair,
            )
            self.assertNotIn('incomplete', pair)
        self.assertIn('data-observation="ssb-cpi-total-2026M07"', body)
        self.assertIn('index 2025=100', body)
        self.assertIn('2026-07-01', body)
        self.assertIn('price index, not a security price', body)
        self.assertIn('data-due="due"', body)
        self.assertNotIn('data-due="current"', body)
        self.assertIn('No revision is stored.', body)
        current = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(current.status, 200)
        self.assertIn(
            'data-source="norges-bank-open-data" data-posture="connected" data-due="current"',
            current.body,
        )
        self.assertIn(
            'data-source="ecb-sdw" data-posture="connected" data-due="current"',
            current.body,
        )
        self.assertIn(CITATION, body)
        self.assertIn('Norges Bank open data', body)
        self.assertIn('Last refresh ' + STAMP + '.', body)
        self.assertIn('synthetic_fixture', body)
        rates = [row['rate'] for row, _posting in self.state.rate_postings]
        self.assertEqual(rates, ['10', '10.25'])
        self.assertNotIn('9.5623', rates)
        self.assertNotIn('4.5', rates)
        self.assertNotIn('4.50', rates)
        self.assertEqual(self.state.ledger.value('2026-03-31'), before_value)
        self.assertEqual(self.state.ledger.books('2026-03-31'), before_books)
        calls = len(transport.urls)
        again = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertEqual(again.status, 200)
        self.assertEqual(len(transport.urls), calls)
        posted = dispatch(self.state, 'POST', '/evidence/refresh', {
            'start_period': '2026-10-01',
            'end_period': '2026-10-09',
        })
        self.assertEqual(posted.status, 200)
        self.assertEqual(len(transport.urls), calls + 6)
        self.assertIn('data-value="9.5623"', posted.body)
        self.assertEqual(self.state.ledger.value('2026-03-31'), before_value)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def _stored_row(self, index, value='1', retrieval='2026-10-11', observation_id=None, observation_time=None):
        from datetime import date as date_cls

        day = date_cls.fromordinal(date_cls(2020, 1, 1).toordinal() + index).isoformat()
        return {
            'observation_id': observation_id or f'id-{index}',
            'source_id': 'norges-bank-open-data',
            'subject': 'USD/NOK',
            'unit': 'NOK per 1 USD',
            'value': value,
            'observation_time': observation_time or day,
            'retrieval_time': retrieval,
            'provenance': 'Norges Bank open data. URL: https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv',
            'quality': ['recorded_fixture'],
        }

    def test_identical_refresh_keeps_one_row_and_a_change_keeps_both(self):
        first = self._stored_row(1, '4.5')
        other = self._stored_row(2, '9.5623')
        write_refresh(self.cache, STAMP, (first, other), ())
        write_refresh(self.cache, STAMP, (dict(first),), ())
        view = read_desk_cache(self.cache)
        self.assertEqual(view.revisions, ())
        self.assertEqual(
            [item['value'] for item in view.observations if item['observation_id'] == 'id-1'],
            ['4.5'],
        )
        self.assertIn('id-2', [item['observation_id'] for item in view.observations])
        changed = self._stored_row(1, '4.25', retrieval='2026-10-12')
        write_refresh(self.cache, STAMP, (changed,), ())
        view = read_desk_cache(self.cache)
        self.assertEqual(len(view.revisions), 1)
        self.assertEqual(view.revisions[0]['observation_id'], 'id-1')
        self.assertEqual(view.revisions[0]['values'], ['4.5', '4.25'])
        self.assertEqual(view.revisions[0]['retrieval_times'], ['2026-10-11', '2026-10-12'])
        self.assertEqual(
            [item['value'] for item in view.observations if item['observation_id'] == 'id-1'],
            ['4.5', '4.25'],
        )
        self.assertIn('id-2', [item['observation_id'] for item in view.observations])
        write_refresh(self.cache, STAMP, (dict(changed),), ())
        view = read_desk_cache(self.cache)
        self.assertEqual(len(view.revisions), 1)
        self.assertEqual(
            [item['value'] for item in view.observations if item['observation_id'] == 'id-1'],
            ['4.5', '4.25'],
        )
        response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(response.body.count('data-revision="id-1"'), 1)
        self.assertIn('Values 4.5, 4.25.', response.body)
        self.assertIn('Retrieval times 2026-10-11, 2026-10-12.', response.body)
        self.assertEqual(self.state.ledger.value('2026-03-31').known_subtotal, Decimal('24932.50'))

    def test_cap_drops_oldest_dates_that_are_absent_from_the_new_batch(self):
        cache = self.cache.parent / 'cap-cache'
        batch = [self._stored_row(index) for index in range(499)]
        batch.append(self._stored_row(0, observation_id='shared-date', observation_time='2026-10-09'))
        write_refresh(cache, STAMP, batch, ())
        self.assertEqual(len(read_desk_cache(cache).observations), 500)
        incoming = self._stored_row(0, '2', observation_id='incoming', observation_time='2026-10-09')
        write_refresh(cache, STAMP, (incoming,), ())
        view = read_desk_cache(cache)
        ids = [item['observation_id'] for item in view.observations]
        self.assertEqual(len(view.observations), 500)
        self.assertNotIn('id-0', ids)
        self.assertIn('id-1', ids)
        self.assertIn('shared-date', ids)
        self.assertIn('incoming', ids)
        wide = self.cache.parent / 'wide-cache'
        write_refresh(wide, STAMP, [self._stored_row(index) for index in range(600)], ())
        self.assertEqual(len(read_desk_cache(wide).observations), 600)
        write_refresh(
            wide,
            STAMP,
            (self._stored_row(0, observation_id='kept-new', observation_time='2026-10-09'),),
            (),
        )
        view = read_desk_cache(wide)
        ids = [item['observation_id'] for item in view.observations]
        self.assertEqual(len(ids), 500)
        self.assertIn('kept-new', ids)
        self.assertNotIn('id-0', ids)
        self.assertNotIn('id-100', ids)
        self.assertIn('id-101', ids)

    def test_recorded_and_live_points_are_labeled_differently(self):
        write_refresh(
            self.cache,
            STAMP,
            (
                {
                    'observation_id': 'nb-exr-USD-NOK-2026-10-08',
                    'source_id': 'norges-bank-open-data',
                    'subject': 'USD/NOK',
                    'unit': 'NOK per 1 USD',
                    'value': '9.5807',
                    'observation_time': '2026-10-08',
                    'retrieval_time': '2026-10-11',
                    'provenance': 'Norges Bank open data. URL: https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv',
                    'quality': ['recorded_fixture'],
                },
                {
                    'observation_id': 'nb-exr-USD-NOK-2026-10-09',
                    'source_id': 'norges-bank-open-data',
                    'subject': 'USD/NOK',
                    'unit': 'NOK per 1 USD',
                    'value': '9.5623',
                    'observation_time': '2026-10-09',
                    'retrieval_time': '2026-10-11',
                    'provenance': 'Norges Bank open data. URL: https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv',
                    'quality': ['live_retrieval'],
                },
            ),
            (),
        )
        response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertEqual(response.status, 200)
        svg = response.body.split('id="usd-nok-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertIn('>recorded<', svg)
        self.assertIn('>live<', svg)
        self.assertIn('data-kind="recorded"', svg)
        self.assertIn('data-kind="live"', svg)
        self.assertNotIn('10.25', svg)
        self.assertNotIn('data-date="2026-03-31"', svg)
        self.assertIn(
            'Rows marked live_retrieval were read from the public source. '
            'Rows marked synthetic_fixture were not. '
            'Neither kind supports a recommendation.',
            response.body,
        )
        self.assertIn(
            'The ledger remains the synthetic book. '
            'Evidence rows are labeled live_retrieval, recorded_fixture, or synthetic_fixture.',
            response.body,
        )

    def test_one_eur_nok_side_is_incomplete_and_prints_no_difference(self):
        write_refresh(
            self.cache,
            STAMP,
            (
                {
                    'observation_id': 'ecb-exr-NOK-EUR-2026-10-08',
                    'source_id': 'ecb-sdw',
                    'subject': 'EUR/NOK',
                    'unit': 'NOK per 1 EUR',
                    'value': '10.717',
                    'observation_time': '2026-10-08',
                    'retrieval_time': '2026-10-11',
                    'provenance': 'Source: ECB statistics.',
                    'quality': ['recorded_fixture'],
                },
            ),
            (),
        )
        before_value = self.state.ledger.value('2026-03-31')
        response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertEqual(response.status, 200)
        pair = response.body.split('data-eur-nok-pair="2026-10-08"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-pair-status="incomplete"', pair)
        self.assertIn('The pair for 2026-10-08 is incomplete.', pair)
        self.assertNotIn('Difference', pair)
        self.assertNotIn('data-difference', pair)
        self.assertNotIn('10.717', pair)
        self.assertEqual(self.state.ledger.value('2026-03-31'), before_value)
        self.assertTrue(self.state.ledger.value('2026-03-31').complete)
        self.assertEqual(
            self.state.ledger.value('2026-03-31').known_subtotal,
            Decimal('24932.50'),
        )

    def test_stored_http_error_is_shown_and_not_retried_as_a_loop(self):
        transport = self._transport(ecb_status=404)
        result = refresh_public(
            self.cache,
            *WINDOW,
            transport=transport,
            retrieved_at=STAMP,
        )
        self.assertEqual(len(transport.urls), 6)
        self.assertEqual(result.errors[0].reason, 'http_status')
        self.assertEqual(result.errors[0].status, 404)
        self.assertEqual(result.errors[0].attempts, 1)
        self.assertTrue(any(row['value'] == '9.5623' for row in result.observations))
        self.assertFalse(any(row['source_id'] == 'ecb-sdw' for row in result.observations))
        response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertIn('data-stored-error="http_status"', response.body)
        self.assertIn('Stored error: http_status.', response.body)
        view = read_desk_cache(self.cache)
        self.assertEqual(view.retrieved_at, STAMP)

    def test_refresh_requires_an_explicit_window_and_does_not_schedule(self):
        def explode(request):
            raise AssertionError(request.url)

        self.state.ingest_transport = explode
        missing = dispatch(self.state, 'POST', '/evidence/refresh', {})
        self.assertEqual(missing.status, 400)
        self.assertIn('explicit start_period and end_period', missing.body)
        blocked = dispatch(self.state, 'GET', '/evidence/refresh', None)
        self.assertEqual(blocked.status, 405)
        still = dispatch(self.state, 'POST', '/evidence', {})
        self.assertEqual(still.status, 405)
        idle = refresh_public(self.cache, *WINDOW, transport=None, explicit_live=False)
        self.assertEqual(idle.errors[0].reason, 'configuration_required')
        self.assertEqual(idle.observations, ())

    def test_ingest_note_records_the_manual_rules(self):
        text = (ROOT / 'docs' / 'INGEST.md').read_text(encoding='utf-8')
        for phrase in (
            'data.norges-bank.no',
            'data-api.ecb.europa.eu',
            'data.ssb.no',
            'data.sec.gov',
            'not_allowlisted',
            '15 seconds',
            '2 seconds',
            'At most 2 retries',
            'IR/K.POL.NOK',
            '404',
            'bounded live query was not locked',
            'table 14700',
            '2026M07',
            '103.8',
            CPI_URL,
            'configuration_required',
            'api_key_and_terms',
            'Refresh is manual',
            'observation_time',
        ):
            self.assertIn(phrase, text)
