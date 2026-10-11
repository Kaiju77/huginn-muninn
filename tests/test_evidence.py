import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.huginn_muninn.desk import (
    INTELLIGENCE,
    _future_kept_note,
    _policy_nowa_section,
    _usd_nok_ledger_section,
)
from src.huginn_muninn.ingest.client import ALLOWLIST
from src.huginn_muninn.evidence import (
    MAX_AGE_DAYS,
    EvidenceStore,
    Observation,
    assess,
    due_status,
    freshness_flags,
    load_registry,
    open_evidence,
    series_inventory,
    source_posture,
    visible_observations,
)
from src.huginn_muninn.ingest.cache import write_refresh
from src.huginn_muninn.prototype import dispatch, open_state


ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / 'fixtures' / 'source_registry.json'
OBSERVATIONS = ROOT / 'fixtures' / 'evidence_observations.json'
AS_OF = date(2026, 3, 31)


def _document():
    return json.loads(OBSERVATIONS.read_text(encoding='utf-8'))


def _first():
    return dict(_document()['observations'][0])


def _store():
    return EvidenceStore(load_registry(REGISTRY), live_retrieval=False)


class EvidenceContractTest(unittest.TestCase):
    def test_registry_records_posture_and_the_assessed_limits(self):
        document = json.loads(REGISTRY.read_text(encoding='utf-8'))
        sources = {row['source_id']: row for row in document['sources']}
        self.assertEqual(len(sources), 6)
        for source in sources.values():
            self.assertIn(source['live_fetch'], (True, False))
            self.assertNotIn('api_key', source)
        self.assertEqual(source_posture(sources['norges-bank-open-data']), 'connected')
        self.assertEqual(source_posture(sources['ecb-sdw']), 'connected')
        self.assertEqual(source_posture(sources['ssb-statbank']), 'connected')
        self.assertEqual(source_posture(sources['sec-edgar-public']), 'prepared')
        self.assertEqual(source_posture(sources['fred']), 'blocked')
        self.assertEqual(source_posture(sources['social-unverified']), 'excluded')
        self.assertIs(sources['norges-bank-open-data']['live_fetch'], True)
        self.assertIs(sources['ecb-sdw']['live_fetch'], True)
        self.assertIs(sources['ssb-statbank']['live_fetch'], True)
        self.assertIs(sources['fred']['live_fetch'], False)
        self.assertIs(sources['sec-edgar-public']['live_fetch'], False)
        self.assertIs(sources['social-unverified']['live_fetch'], False)
        self.assertEqual(sources['norges-bank-open-data']['publisher'], 'Norges Bank')
        self.assertEqual(sources['norges-bank-open-data']['category'], 'official_statistics')
        self.assertEqual(sources['norges-bank-open-data']['cadence'], 'periodic')
        self.assertIn(
            'They are not equity prices and not executable quotes.',
            sources['norges-bank-open-data']['description'],
        )
        self.assertIn('requires no authentication', sources['norges-bank-open-data']['description'])
        self.assertEqual(sources['ssb-statbank']['publisher'], 'Statistics Norway')
        self.assertIn('CC BY 4.0', sources['ssb-statbank']['description'])
        self.assertIn('800000', sources['ssb-statbank']['description'])
        self.assertIn('30 queries per minute', sources['ssb-statbank']['description'])
        self.assertIn('not security prices', sources['ssb-statbank']['description'])
        self.assertIn('14700', sources['ssb-statbank']['description'])
        self.assertIn('2026M07', sources['ssb-statbank']['description'])
        self.assertIn('Other SSB tables remain unconnected', sources['ssb-statbank']['description'])
        self.assertEqual(sources['fred']['blocked_reason'], 'api_key_and_terms')
        self.assertIn('training machine-learning models', sources['fred']['description'])
        self.assertIn('not a real-time trading feed', sources['fred']['description'])
        self.assertEqual(sources['sec-edgar-public']['category'], 'filings')
        self.assertIn('10 requests per second', sources['sec-edgar-public']['description'])
        self.assertIn('Filings are not live prices.', sources['sec-edgar-public']['description'])
        self.assertEqual(sources['ecb-sdw']['license_status'], 'verified_free_reuse_with_citation')
        self.assertIn(
            'https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html',
            sources['ecb-sdw']['references'],
        )
        self.assertIn('figures are not modified', sources['ecb-sdw']['description'])
        self.assertEqual(sources['social-unverified']['publisher'], 'none')
        self.assertEqual(sources['social-unverified']['category'], 'excluded')
        self.assertEqual(sources['social-unverified']['status'], 'excluded')
        self.assertEqual(
            sources['social-unverified']['reason'],
            'unverified social-media sentiment is not market evidence',
        )
        fixture = _document()
        self.assertIs(fixture['live_retrieval'], False)

    def test_locked_freshness(self):
        store = open_evidence(ROOT)
        by_id = {item.observation_id: item for item in store.observations()}
        fresh = freshness_flags(by_id['obs-usd-nok-2026-03-31'], AS_OF, MAX_AGE_DAYS)
        stale = freshness_flags(by_id['obs-stale-policy'], AS_OF, MAX_AGE_DAYS)
        self.assertEqual(fresh, ('fresh',))
        self.assertEqual(stale, ('stale',))
        self.assertEqual(by_id['obs-usd-nok-2026-03-31'].value, Decimal('10.25'))
        self.assertEqual(by_id['obs-stale-policy'].value, Decimal('4.50'))
        self.assertNotEqual(by_id['obs-stale-policy'].value, Decimal('0'))
        self.assertEqual(by_id['obs-usd-nok-2026-03-31'].quality, ('synthetic_fixture',))

    def test_second_copy_is_one_stored_row(self):
        store = open_evidence(ROOT)
        result = store.ingest(_first())
        self.assertTrue(result.duplicate)
        self.assertFalse(result.stored)
        self.assertFalse(result.conflict)
        self.assertEqual(len(store.observations()), 2)
        self.assertEqual(
            [item.observation_id for item in store.observations()].count('obs-usd-nok-2026-03-31'),
            1,
        )
        bare = _store()
        row = _first()
        self.assertTrue(bare.ingest(row).stored)
        self.assertTrue(bare.ingest(dict(row)).duplicate)
        spelled = dict(row)
        spelled['value'] = '10.250'
        self.assertTrue(bare.ingest(spelled).duplicate)
        self.assertEqual(len(bare.observations()), 1)
        self.assertEqual(bare.observations()[0].value, Decimal('10.25'))

    def test_same_value_different_observation_time_is_a_conflict(self):
        store = open_evidence(ROOT)
        row = _first()
        row['observation_time'] = '2026-04-01'
        result = store.ingest(row)
        self.assertTrue(result.conflict)
        self.assertFalse(result.stored)
        self.assertFalse(result.duplicate)
        conflict = store.conflicts()[0]
        self.assertEqual(
            conflict.observation_times,
            (date(2026, 3, 31), date(2026, 4, 1)),
        )
        self.assertEqual(conflict.values, (Decimal('10.25'), Decimal('10.25')))
        stored = [
            item for item in store.observations()
            if item.observation_id == 'obs-usd-nok-2026-03-31'
        ]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].observation_time, date(2026, 3, 31))
        self.assertEqual(stored[0].value, Decimal('10.25'))
        visible = [
            item for item in visible_observations(store)
            if item.observation_id == 'obs-usd-nok-2026-03-31'
        ]
        self.assertEqual(
            [item.observation_time for item in visible],
            [date(2026, 3, 31), date(2026, 4, 1)],
        )
        self.assertTrue(store.ingest(dict(row)).duplicate)
        self.assertEqual(len(store.conflicts()[0].observation_times), 2)

    def test_conflicting_value_keeps_both_amounts_and_the_ledger_rate(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = open_state(ROOT, Path(temporary.name) / 'synthetic-book.json')
        before_value = state.ledger.value('2026-03-31')
        before_books = state.ledger.books('2026-03-31')
        rates = [row['rate'] for row, _posting in state.rate_postings]
        store = open_evidence(ROOT)
        conflict = _first()
        conflict['value'] = '10.26'
        result = store.ingest(conflict)
        self.assertTrue(result.conflict)
        self.assertFalse(result.stored)
        stored = [
            item for item in store.observations()
            if item.observation_id == 'obs-usd-nok-2026-03-31'
        ]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].value, Decimal('10.25'))
        self.assertEqual(store.conflicts()[0].values, (Decimal('10.25'), Decimal('10.26')))
        self.assertEqual(state.ledger.value('2026-03-31'), before_value)
        self.assertEqual(state.ledger.books('2026-03-31'), before_books)
        self.assertEqual(
            [row['rate'] for row, _posting in state.rate_postings],
            rates,
        )
        self.assertEqual(rates, ['10', '10.25'])
        self.assertNotIn('10.26', rates)
        assessed = assess(store, AS_OF)
        self.assertIn('conflict', assessed.limitations)
        self.assertEqual(assessed._fields, ('limitations',))

    def test_non_finite_values_are_rejected(self):
        store = open_evidence(ROOT)
        for text in ('NaN', 'Infinity', '-Infinity'):
            row = _first()
            row['value'] = text
            result = store.ingest(row)
            self.assertFalse(result.stored)
            self.assertFalse(result.conflict)
            self.assertIn('non_finite', result.reasons)
        stored = [
            item for item in store.observations()
            if item.observation_id == 'obs-usd-nok-2026-03-31'
        ]
        self.assertEqual(stored[0].value, Decimal('10.25'))
        self.assertEqual(store.conflicts(), ())
        self.assertTrue(stored[0].value.is_finite())

    def test_json_numbers_are_rejected(self):
        store = open_evidence(ROOT)
        for number in (10.25, 10, True):
            row = _first()
            row['value'] = number
            result = store.ingest(row)
            self.assertFalse(result.stored)
            self.assertFalse(result.conflict)
            self.assertIn('json_number', result.reasons)
        parsed = json.loads('{"value": 10.26}')
        row = _first()
        row['value'] = parsed['value']
        result = store.ingest(row)
        self.assertIn('json_number', result.reasons)
        self.assertFalse(result.conflict)
        stored = [
            item for item in store.observations()
            if item.observation_id == 'obs-usd-nok-2026-03-31'
        ]
        self.assertEqual(stored[0].value, Decimal('10.25'))
        self.assertEqual(store.conflicts(), ())

    def test_blank_provenance_is_not_stored(self):
        store = _store()
        row = _first()
        row['observation_id'] = 'obs-blank'
        row['provenance'] = '   '
        result = store.ingest(row)
        self.assertFalse(result.stored)
        self.assertIn('blank_provenance', result.reasons)
        self.assertEqual(store.observations(), ())

    def test_missing_value_is_not_fresh_and_is_not_zero(self):
        store = _store()
        row = _first()
        row['observation_id'] = 'obs-missing'
        row['value'] = None
        result = store.ingest(row)
        self.assertTrue(result.stored)
        observation = store.observations()[0]
        self.assertIsNone(observation.value)
        self.assertNotEqual(observation.value, Decimal('0'))
        flags = freshness_flags(observation, AS_OF, MAX_AGE_DAYS)
        self.assertIn('missing_value', flags)
        self.assertNotIn('fresh', flags)

    def test_future_dates_and_the_age_boundary(self):
        store = _store()
        boundary = _first()
        boundary['observation_id'] = 'obs-boundary'
        boundary['observation_time'] = '2026-03-24'
        boundary['retrieval_time'] = '2026-03-24'
        self.assertTrue(store.ingest(boundary).stored)
        older = _first()
        older['observation_id'] = 'obs-older'
        older['observation_time'] = '2026-03-23'
        older['retrieval_time'] = '2026-03-23'
        self.assertTrue(store.ingest(older).stored)
        future = _first()
        future['observation_id'] = 'obs-future'
        future['observation_time'] = '2026-04-01'
        future['retrieval_time'] = '2026-04-02'
        self.assertTrue(store.ingest(future).stored)
        late_retrieval = _first()
        late_retrieval['observation_id'] = 'obs-late-retrieval'
        late_retrieval['observation_time'] = '2026-03-31'
        late_retrieval['retrieval_time'] = '2026-04-01'
        self.assertTrue(store.ingest(late_retrieval).stored)
        by_id = {item.observation_id: item for item in store.observations()}
        self.assertEqual(freshness_flags(by_id['obs-boundary'], AS_OF, 7), ('fresh',))
        self.assertEqual(freshness_flags(by_id['obs-older'], AS_OF, 7), ('stale',))
        self.assertEqual(
            freshness_flags(by_id['obs-future'], AS_OF, 7),
            ('future_observation', 'future_retrieval'),
        )
        self.assertEqual(
            freshness_flags(by_id['obs-late-retrieval'], AS_OF, 7),
            ('future_retrieval',),
        )

    def test_social_source_is_excluded(self):
        store = open_evidence(ROOT)
        row = _first()
        row['observation_id'] = 'obs-social'
        row['source_id'] = 'social-unverified'
        row['subject'] = 'mood'
        result = store.ingest(row)
        self.assertFalse(result.stored)
        self.assertIn('excluded', result.reasons)
        self.assertFalse(any(
            item.source_id == 'social-unverified' for item in store.observations()
        ))
        assessed = assess(store, AS_OF)
        self.assertIn('excluded social source', assessed.limitations)

    def test_synthetic_rows_do_not_make_a_connected_source_current(self):
        store = open_evidence(ROOT)
        statuses = dict(due_status(store.sources(), store.observations(), AS_OF))
        self.assertEqual(statuses['norges-bank-open-data'], 'due')
        self.assertEqual(statuses['ecb-sdw'], 'due')
        self.assertEqual(statuses['ssb-statbank'], 'due')
        self.assertNotIn('fred', statuses)
        row = _first()
        row['observation_id'] = 'nb-exr-USD-NOK-2026-03-31'
        row['quality'] = ['recorded_fixture']
        row['provenance'] = (
            'Norges Bank open data. URL: '
            'https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=csv'
        )
        self.assertTrue(store.ingest(row).stored)
        statuses = dict(due_status(store.sources(), store.observations(), AS_OF))
        self.assertEqual(statuses['norges-bank-open-data'], 'current')
        self.assertEqual(statuses['ecb-sdw'], 'due')
        self.assertEqual(statuses['ssb-statbank'], 'due')

    def test_assess_returns_limitations_only(self):
        store = open_evidence(ROOT)
        result = assess(store, AS_OF)
        self.assertEqual(
            result.limitations,
            (
                'synthetic fixture',
                'stale',
                'source not connected',
                'excluded social source',
            ),
        )
        self.assertEqual(result._fields, ('limitations',))
        self.assertFalse(hasattr(result, 'recommendation'))
        self.assertFalse(hasattr(result, 'probability'))
        rendered = ' '.join(result.limitations)
        self.assertNotIn('probability', rendered)
        for word in ('buy', 'sell', 'hold', 'rebalance'):
            self.assertNotIn(word, rendered)

    def test_cache_replay_keeps_the_conflict(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        cache = Path(temporary.name) / 'evidence-cache.json'
        sources = load_registry(REGISTRY)
        store = EvidenceStore(sources, cache_path=cache, live_retrieval=False)
        row = _first()
        self.assertTrue(store.ingest(row).stored)
        self.assertTrue(store.ingest(dict(row)).duplicate)
        conflict = dict(row)
        conflict['value'] = '10.26'
        self.assertTrue(store.ingest(conflict).conflict)
        reloaded = EvidenceStore(sources, cache_path=cache, live_retrieval=False)
        reloaded.load_cache()
        self.assertEqual(len(reloaded.observations()), 1)
        self.assertEqual(reloaded.observations()[0].value, Decimal('10.25'))
        self.assertEqual(reloaded.conflicts()[0].values, (Decimal('10.25'), Decimal('10.26')))
        self.assertIn('conflict', assess(reloaded, AS_OF).limitations)

    def test_series_inventory_lists_each_visible_subject_once(self):
        store = open_evidence(ROOT)
        lines = {
            line.subject: line
            for line in series_inventory(visible_observations(store))
        }
        self.assertEqual(set(lines), {'USD/NOK', 'policy-rate'})
        self.assertEqual(lines['USD/NOK'].source_ids, ('norges-bank-open-data',))
        self.assertEqual(lines['USD/NOK'].latest_date, date(2026, 3, 31))
        self.assertEqual(lines['USD/NOK'].values, (Decimal('10.25'),))
        self.assertEqual(lines['USD/NOK'].retrieval_dates, (date(2026, 3, 31),))
        self.assertEqual(lines['policy-rate'].latest_date, date(2026, 1, 2))
        self.assertEqual(lines['policy-rate'].values, (Decimal('4.50'),))
        self.assertEqual(lines['policy-rate'].retrieval_dates, (date(2026, 1, 2),))
        self.assertEqual(series_inventory(()), ())
        conflict = _first()
        conflict['value'] = '10.26'
        self.assertTrue(store.ingest(conflict).conflict)
        lines = {
            line.subject: line
            for line in series_inventory(visible_observations(store))
        }
        self.assertEqual(
            lines['USD/NOK'].values,
            (Decimal('10.25'), Decimal('10.26')),
        )
        self.assertEqual(
            lines['USD/NOK'].retrieval_dates,
            (date(2026, 3, 31), date(2026, 3, 31)),
        )
        self.assertEqual(lines['USD/NOK'].latest_date, date(2026, 3, 31))
        later = _first()
        later['observation_id'] = 'nb-exr-USD-NOK-2026-10-09'
        later['observation_time'] = '2026-10-09'
        later['retrieval_time'] = '2026-10-11'
        later['value'] = '9.5623'
        later['quality'] = ['recorded_fixture']
        later['provenance'] = 'Norges Bank open data.'
        self.assertTrue(store.ingest(later).stored)
        lines = {
            line.subject: line
            for line in series_inventory(visible_observations(store))
        }
        self.assertEqual(lines['USD/NOK'].latest_date, date(2026, 10, 9))
        self.assertEqual(lines['USD/NOK'].values, (Decimal('9.5623'),))
        self.assertEqual(lines['USD/NOK'].retrieval_dates, (date(2026, 10, 11),))
        self.assertEqual(len(lines), 2)

    def test_shared_latest_date_keeps_both_values_for_one_subject(self):
        store = _store()
        rows = (
            ('norges-bank-open-data', 'nb-exr-EUR-NOK-2026-10-09', '10.7155', '2026-10-09', '2026-10-12'),
            ('ecb-sdw', 'ecb-exr-NOK-EUR-2026-10-09', '10.717', '2026-10-09', '2026-10-11'),
            ('norges-bank-open-data', 'nb-exr-EUR-NOK-2026-10-08', '10.700', '2026-10-08', '2026-10-10'),
        )
        for source_id, observation_id, value, observed, retrieved in rows:
            row = _first()
            row['observation_id'] = observation_id
            row['source_id'] = source_id
            row['subject'] = 'EUR/NOK'
            row['unit'] = 'NOK per 1 EUR'
            row['value'] = value
            row['observation_time'] = observed
            row['retrieval_time'] = retrieved
            row['provenance'] = 'recorded'
            row['quality'] = ['recorded_fixture']
            self.assertTrue(store.ingest(row).stored)
        found = series_inventory(visible_observations(store))
        self.assertEqual(len(found), 1)
        line = found[0]
        self.assertEqual(line.subject, 'EUR/NOK')
        self.assertEqual(line.source_ids, ('ecb-sdw', 'norges-bank-open-data'))
        self.assertEqual(line.latest_date, date(2026, 10, 9))
        self.assertEqual(line.values, (Decimal('10.717'), Decimal('10.7155')))
        self.assertEqual(
            line.retrieval_dates,
            (date(2026, 10, 11), date(2026, 10, 12)),
        )
        self.assertEqual(tuple(item.value for item in line.rows), line.values)
        self.assertEqual(
            tuple(item.retrieval_time for item in line.rows),
            line.retrieval_dates,
        )
        self.assertEqual(len(line.retrieval_dates), len(line.values))
        self.assertNotIn(date(2026, 10, 10), line.retrieval_dates)
        self.assertNotIn(Decimal('10.700'), line.values)

    def test_cpi_observation_stays_stale_on_2026_10_11(self):
        store = _store()
        row = _first()
        row['observation_id'] = 'ssb-cpi-total-2026M07'
        row['source_id'] = 'ssb-statbank'
        row['subject'] = 'cpi-total'
        row['unit'] = 'index 2025=100'
        row['value'] = '103.8'
        row['observation_time'] = '2026-07-01'
        row['retrieval_time'] = '2026-10-11'
        row['provenance'] = 'Statistics Norway. Table 14700.'
        row['quality'] = ['recorded_fixture']
        self.assertTrue(store.ingest(row).stored)
        flags = freshness_flags(store.observations()[0], date(2026, 10, 11), MAX_AGE_DAYS)
        self.assertEqual(flags, ('stale',))
        self.assertNotIn('fresh', flags)
        self.assertEqual(MAX_AGE_DAYS, 7)

    def test_evidence_module_does_not_mention_network_libraries(self):
        source = (ROOT / 'src' / 'huginn_muninn' / 'evidence.py').read_text(encoding='utf-8')
        self.assertNotIn('urllib', source)
        self.assertNotIn('requests', source)
        self.assertNotIn('socket', source)
        self.assertNotIn('http.client', source)


class EvidencePageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.overlay = Path(self._tmp.name) / 'synthetic-book.json'
        self.state = open_state(ROOT, self.overlay)
        self.state.ingest_cache_dir = Path(self._tmp.name) / 'ingest-cache'

    def tearDown(self):
        self._tmp.cleanup()

    def test_evidence_page_renders_the_fixture_without_changing_the_ledger(self):
        before_value = self.state.ledger.value('2026-03-31')
        before_books = self.state.ledger.books('2026-03-31')
        response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertEqual(response.status, 200)
        self.assertIn('text/html', response.content_type)
        body = response.body
        self.assertIn('The desk is in research mode.', body)
        self.assertNotIn('No source is connected.', body)
        self.assertIn('This page is not a recommendation.', body)
        self.assertIn('No live refresh has been stored.', body)
        self.assertEqual(
            body.count('A later calendar day is not a scheduled refresh.'),
            1,
        )
        self.assertIn('No stored error.', body)
        self.assertIn('Refresh is manual. It is not a scheduler.', body)
        self.assertIn(
            'Loaded evidence is a recorded synthetic fixture. '
            'It does not support a recommendation.',
            body,
        )
        self.assertIn('href="/evidence"', body)
        self.assertIn('data-source="norges-bank-open-data" data-posture="connected"', body)
        self.assertIn('data-source="ecb-sdw" data-posture="connected"', body)
        self.assertIn(
            'data-source="ssb-statbank" data-posture="connected" data-due="due"',
            body,
        )
        self.assertIn('data-source="sec-edgar-public" data-posture="prepared"', body)
        self.assertIn('data-source="fred" data-posture="blocked"', body)
        self.assertIn('data-source="social-unverified" data-posture="excluded"', body)
        self.assertEqual(body.count('live_fetch false'), 3)
        self.assertEqual(body.count('live_fetch true'), 3)
        self.assertIn('api_key_and_terms', body)
        self.assertIn('verified_free_reuse_with_citation', body)
        self.assertNotIn('not_verified_this_increment', body)
        self.assertIn('unverified social-media sentiment is not market evidence', body)
        self.assertIn('They are not equity prices and not executable quotes.', body)
        self.assertIn('not security prices', body)
        self.assertIn('Filings are not live prices.', body)
        self.assertIn('training machine-learning models', body)
        self.assertIn('data-observation="obs-usd-nok-2026-03-31" data-freshness="fresh"', body)
        self.assertIn('data-observation="obs-stale-policy" data-freshness="stale"', body)
        usd_series = body.split('data-series-subject="USD/NOK"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-source-id="norges-bank-open-data"', usd_series)
        self.assertIn('data-latest="2026-03-31"', usd_series)
        self.assertIn('data-values="10.25"', usd_series)
        self.assertIn('data-retrieval-dates="2026-03-31"', usd_series)
        self.assertIn('Latest observation date 2026-03-31.', usd_series)
        self.assertIn('Value 10.25.', usd_series)
        self.assertIn('Retrieved 2026-03-31.', usd_series)
        self.assertIn('data-freshness="fresh"', usd_series)
        self.assertIn('Freshness fresh.', usd_series)
        self.assertNotIn('The date has more than one row.', usd_series)
        policy_series = body.split('data-series-subject="policy-rate"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-latest="2026-01-02"', policy_series)
        self.assertIn('data-values="4.50"', policy_series)
        self.assertIn('data-retrieval-dates="2026-01-02"', policy_series)
        self.assertIn('Retrieved 2026-01-02.', policy_series)
        self.assertIn('data-freshness="stale"', policy_series)
        self.assertIn('Freshness stale.', policy_series)
        self.assertNotIn('Freshness fresh', policy_series)
        self.assertNotIn('The date has more than one row.', policy_series)
        self.assertEqual(body.count('data-series-subject='), 2)
        self.assertIn('Computed from stored rows.', body)
        self.assertNotIn(
            'The CPI date is the first day of 2026M07. '
            'Stale in October means the monthly index is older than 7 days. '
            'It is not a failed daily refresh.',
            body,
        )
        self.assertIn('synthetic-fixture-not-a-live-norges-bank-retrieval', body)
        self.assertIn(
            'The synthetic 10.25 fixture is labeled synthetic and is not drawn as a Norges Bank point.',
            body,
        )
        svg = body.split('id="usd-nok-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertNotIn('10.25', svg)
        self.assertNotIn('2026-03-31', svg)
        self.assertNotIn('9.5623', svg)
        self.assertNotIn('data-value="4.50"', svg)
        policy = body.split('id="policy-rate-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertNotIn('4.50', policy)
        self.assertNotIn('2026-01-02', policy)
        self.assertNotIn('data-value="4.5"', policy)
        nowa = body.split('id="nowa-ingested"', 1)[1].split('</svg>', 1)[0]
        self.assertNotIn('4.50', nowa)
        self.assertNotIn('2026-01-02', nowa)
        self.assertNotIn('10.25', nowa)
        self.assertNotIn('9.5623', nowa)
        self.assertNotIn('10.717', nowa)
        self.assertIn(
            'No stored date has both a Norges Bank EUR/NOK observation '
            'and an ECB NOK/EUR observation.',
            body,
        )
        self.assertIn(
            'data-source="norges-bank-open-data" data-posture="connected" data-due="due"',
            body,
        )
        self.assertIn(
            'data-source="ecb-sdw" data-posture="connected" data-due="due"',
            body,
        )
        self.assertNotIn('data-due="current"', body)
        self.assertNotIn('data-source="fred" data-posture="blocked" data-due=', body)
        self.assertIn('No revision is stored.', body)
        self.assertIn(
            "The number matches the ledger's supplied 10.25 rate. "
            'The match is not a live source confirmation.',
            body,
        )
        ledger_note = body.split('id="usd-nok-ledger"', 1)[1].split('</section>', 1)[0]
        self.assertIn('data-ledger-rate="10.25"', ledger_note)
        self.assertIn('data-observation-id="obs-usd-nok-2026-03-31"', ledger_note)
        self.assertIn('data-stored-value="10.25"', ledger_note)
        self.assertIn('data-observation-date="2026-03-31"', ledger_note)
        self.assertIn('data-quality="synthetic_fixture"', ledger_note)
        self.assertIn('data-equals="true"', ledger_note)
        self.assertIn('Newest stored observation 10.25.', ledger_note)
        self.assertIn('Observation date 2026-03-31.', ledger_note)
        self.assertIn('Quality synthetic_fixture.', ledger_note)
        self.assertIn('Ledger rate 10.25.', ledger_note)
        self.assertIn('The stored value equals 10.25.', ledger_note)
        self.assertIn('A match and a gap are not a ledger update.', ledger_note)
        self.assertEqual(body.count('A match and a gap are not a ledger update.'), 1)
        self.assertNotIn('The date has more than one row.', ledger_note)
        self.assertNotIn('data-multiple', ledger_note)
        pair = body.split('id="policy-nowa"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(pair.count('The policy rate and NOWA are not combined.'), 1)
        self.assertEqual(body.count('The policy rate and NOWA are not combined.'), 1)
        policy_note = pair.split('data-subject="policy-rate"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-visible="true"', policy_note)
        self.assertIn('data-latest="2026-01-02"', policy_note)
        self.assertIn('data-values="4.50"', policy_note)
        self.assertIn('Latest observation date 2026-01-02.', policy_note)
        self.assertIn('Value 4.50.', policy_note)
        self.assertNotIn('The date has more than one row.', policy_note)
        nowa_note = pair.split('data-subject="nowa"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-visible="false"', nowa_note)
        self.assertIn('nowa is not visible.', nowa_note)
        self.assertNotIn('Value ', nowa_note)
        hosts = body.split('id="allowlist-hosts"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(
            hosts.count(
                'These hosts are the allowlist. This page does not open a connection.'
            ),
            1,
        )
        listed = hosts.split('<ul>', 1)[1].split('</ul>', 1)[0]
        self.assertEqual(
            listed,
            ''.join(f'<li>{host}</li>' for host in sorted(ALLOWLIST)),
        )
        self.assertNotIn(
            'A row later than the selected date stays on the page. It was not dropped.',
            body,
        )
        self.assertNotIn('No stored USD/NOK observation is visible.', body)
        self.assertIn('4.50', body)
        self.assertNotIn('probability', body.lower())
        self.assertEqual(self.state.ledger.value('2026-03-31'), before_value)
        self.assertEqual(self.state.ledger.books('2026-03-31'), before_books)
        self.assertEqual(before_value.known_subtotal, Decimal('24932.50'))
        rates = [row['rate'] for row, _posting in self.state.rate_postings]
        self.assertEqual(rates, ['10', '10.25'])
        selected = dispatch(self.state, 'GET', '/evidence?date=2026-01-02', None)
        self.assertEqual(selected.status, 200)
        self.assertIn('Freshness against 2026-01-02.', selected.body)
        selected_usd = selected.body.split('data-series-subject="USD/NOK"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-latest="2026-03-31"', selected_usd)
        self.assertIn(
            'data-freshness="future_observation future_retrieval"',
            selected_usd,
        )
        self.assertIn(
            'Freshness future_observation future_retrieval.',
            selected_usd,
        )
        self.assertNotIn('Freshness fresh', selected_usd)
        self.assertIn(
            'data-observation="obs-stale-policy" data-freshness="fresh"',
            selected.body,
        )
        self.assertIn(
            'data-observation="obs-usd-nok-2026-03-31" '
            'data-freshness="future_observation future_retrieval"',
            selected.body,
        )
        self.assertNotIn(
            'data-observation="obs-usd-nok-2026-03-31" data-freshness="fresh"',
            selected.body,
        )
        self.assertEqual(
            selected.body.count(
                'A row later than the selected date stays on the page. It was not dropped.'
            ),
            1,
        )
        self.assertIn(
            'The match is not a live source confirmation.',
            selected.body,
        )
        later = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(later.status, 200)
        self.assertIn(
            'data-observation="obs-usd-nok-2026-03-31" data-freshness="stale"',
            later.body,
        )
        self.assertNotIn(
            'A row later than the selected date stays on the page. It was not dropped.',
            later.body,
        )
        later_note = later.body.split('id="usd-nok-ledger"', 1)[1].split('</section>', 1)[0]
        self.assertIn('data-stored-value="10.25"', later_note)
        self.assertIn('data-gap="0"', later_note)
        self.assertIn('Gap 0. The USD/NOK gap is not a recommendation and is not copied into the ledger.', later_note)
        self.assertNotIn('Gap 0.000', later_note)
        self.assertIn('A match and a gap are not a ledger update.', later_note)
        later_usd = later.body.split('data-series-subject="USD/NOK"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-freshness="stale"', later_usd)
        self.assertIn('Freshness stale.', later_usd)
        self.assertNotIn('Freshness fresh', later_usd)
        rejected = dispatch(self.state, 'GET', '/evidence?date=2026-02-31', None)
        self.assertEqual(rejected.status, 400)
        blocked = dispatch(self.state, 'POST', '/evidence', {})
        self.assertEqual(blocked.status, 405)

    def test_desk_home_keeps_the_synthetic_total_and_the_fixture_sentence(self):
        response = dispatch(self.state, 'GET', '/', None)
        self.assertEqual(response.status, 200)
        self.assertIn('15050', response.body)
        self.assertIn('synthetic', response.body.lower())
        self.assertIn('not a recommendation', response.body.lower())
        self.assertIn('href="/evidence"', response.body)
        for sentence in INTELLIGENCE:
            self.assertIn(sentence, response.body)
        self.assertIn(
            'Loaded evidence is a recorded synthetic fixture. It does not support a recommendation.',
            response.body,
        )
        self.assertIn('Confidence is not assessed.', response.body)
        self.assertIn('Risk is not assessed. No risk model is loaded.', response.body)
        self.assertIn('The recorded fixture is not a competing interpretation. No interpretation is offered.', response.body)
        self.assertIn('No forecast is computed.', response.body)

    def test_cpi_sentence_is_shown_and_the_october_row_stays_stale(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T09:21:00+00:00',
            ({
                'observation_id': 'ssb-cpi-total-2026M07',
                'source_id': 'ssb-statbank',
                'subject': 'cpi-total',
                'unit': 'index 2025=100',
                'value': '103.8',
                'observation_time': '2026-07-01',
                'retrieval_time': '2026-10-11',
                'provenance': (
                    'Statistics Norway. CC BY 4.0. Table 14700. '
                    'This is a price index, not a security price.'
                ),
                'quality': ['recorded_fixture'],
            },),
            (),
        )
        before = self.state.ledger.value('2026-03-31')
        response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(response.status, 200)
        sentence = (
            'The CPI date is the first day of 2026M07. '
            'Stale in October means the monthly index is older than 7 days. '
            'It is not a failed daily refresh.'
        )
        self.assertEqual(response.body.count(sentence), 1)
        self.assertIn(
            'data-observation="ssb-cpi-total-2026M07" data-freshness="stale"',
            response.body,
        )
        self.assertNotIn(
            'data-observation="ssb-cpi-total-2026M07" data-freshness="fresh"',
            response.body,
        )
        cpi = response.body.split('data-series-subject="cpi-total"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-source-id="ssb-statbank"', cpi)
        self.assertIn('data-latest="2026-07-01"', cpi)
        self.assertIn('data-values="103.8"', cpi)
        self.assertIn('data-retrieval-dates="2026-10-11"', cpi)
        self.assertIn('Value 103.8.', cpi)
        self.assertIn('Retrieved 2026-10-11.', cpi)
        self.assertIn('data-freshness="stale"', cpi)
        self.assertIn('Freshness stale.', cpi)
        self.assertNotIn('Freshness fresh', cpi)
        self.assertNotIn('Retrieved 2026-07-01.', cpi)
        self.assertNotIn('data-multiple', cpi)
        self.assertNotIn('The date has more than one row.', cpi)
        self.assertIn(
            'data-source="ssb-statbank" data-posture="connected" data-due="due"',
            response.body,
        )
        self.assertEqual(self.state.ledger.value('2026-03-31'), before)
        self.assertEqual(before.known_subtotal, Decimal('24932.50'))
        rates = [row['rate'] for row, _posting in self.state.rate_postings]
        self.assertEqual(rates, ['10', '10.25'])

    def test_inventory_shows_both_values_when_the_latest_date_has_two_rows(self):
        rows = []
        samples = (
            ('norges-bank-open-data', 'nb-exr-EUR-NOK-2026-10-09', '10.7155', '2026-10-09', '2026-10-12'),
            ('ecb-sdw', 'ecb-exr-NOK-EUR-2026-10-09', '10.717', '2026-10-09', '2026-10-11'),
            ('norges-bank-open-data', 'nb-exr-EUR-NOK-2026-10-08', '10.700', '2026-10-08', '2026-10-10'),
        )
        for source_id, observation_id, value, observed, retrieved in samples:
            rows.append({
                'observation_id': observation_id,
                'source_id': source_id,
                'subject': 'EUR/NOK',
                'unit': 'NOK per 1 EUR',
                'value': value,
                'observation_time': observed,
                'retrieval_time': retrieved,
                'provenance': 'recorded',
                'quality': ['recorded_fixture'],
            })
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T09:21:00+00:00',
            tuple(rows),
            (),
        )
        before = self.state.ledger.value('2026-03-31')
        response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(response.status, 200)
        line = response.body.split('data-series-subject="EUR/NOK"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-source-id="ecb-sdw norges-bank-open-data"', line)
        self.assertIn('data-latest="2026-10-09"', line)
        self.assertIn('data-values="10.717 10.7155"', line)
        self.assertIn('data-retrieval-dates="2026-10-11 2026-10-12"', line)
        self.assertIn('data-multiple="true"', line)
        self.assertIn('Source ecb-sdw.', line)
        self.assertIn('Source norges-bank-open-data.', line)
        self.assertIn('Value 10.717.', line)
        self.assertIn('Value 10.7155.', line)
        self.assertIn('Retrieved 2026-10-11.', line)
        self.assertIn('Retrieved 2026-10-12.', line)
        self.assertIn('data-freshness="fresh, future_retrieval"', line)
        self.assertIn('Freshness fresh. Freshness future_retrieval.', line)
        self.assertNotIn('Freshness fresh. Freshness fresh.', line)
        self.assertLess(line.index('Value 10.717.'), line.index('Value 10.7155.'))
        self.assertLess(line.index('Value 10.7155.'), line.index('Freshness fresh.'))
        self.assertLess(
            line.index('Freshness fresh.'),
            line.index('Freshness future_retrieval.'),
        )
        self.assertLess(line.index('Value 10.717.'), line.index('Retrieved 2026-10-11.'))
        self.assertLess(line.index('Retrieved 2026-10-11.'), line.index('Retrieved 2026-10-12.'))
        self.assertIn('The date has more than one row.', line)
        self.assertNotIn('10.700', line)
        self.assertNotIn('2026-10-10', line)
        usd = response.body.split('data-series-subject="USD/NOK"', 1)[1].split('</p>', 1)[0]
        self.assertNotIn('The date has more than one row.', usd)
        self.assertNotIn(
            'The CPI date is the first day of 2026M07.',
            response.body,
        )
        self.assertEqual(self.state.ledger.value('2026-03-31'), before)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def _usd_row(self, observation_id, value, observed, quality, retrieval='2026-10-11'):
        return {
            'observation_id': observation_id,
            'source_id': 'norges-bank-open-data',
            'subject': 'USD/NOK',
            'unit': 'NOK per 1 USD',
            'value': value,
            'observation_time': observed,
            'retrieval_time': retrieval,
            'provenance': 'Norges Bank open data.',
            'quality': quality,
        }

    def _ledger_section(self, body):
        return body.split('id="usd-nok-ledger"', 1)[1].split('</section>', 1)[0]

    def test_newest_usd_nok_date_beats_the_older_fixture(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T08:03:34+00:00',
            (self._usd_row(
                'nb-exr-USD-NOK-2026-10-09',
                '9.5623',
                '2026-10-09',
                ['live_retrieval'],
            ),),
            (),
        )
        before = self.state.ledger.value('2026-03-31')
        response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(response.status, 200)
        note = self._ledger_section(response.body)
        self.assertIn('data-ledger-rate="10.25"', note)
        self.assertIn('data-observation-id="nb-exr-USD-NOK-2026-10-09"', note)
        self.assertIn('data-stored-value="9.5623"', note)
        self.assertIn('data-observation-date="2026-10-09"', note)
        self.assertIn('data-quality="live_retrieval"', note)
        self.assertIn('data-equals="false"', note)
        self.assertIn('Newest stored observation 9.5623.', note)
        self.assertNotIn('Newest stored observation 10.25.', note)
        self.assertIn('Observation date 2026-10-09.', note)
        self.assertIn('Quality live_retrieval.', note)
        self.assertIn('Ledger rate 10.25.', note)
        self.assertIn('The stored value does not equal 10.25.', note)
        self.assertIn('data-gap="-0.6877"', note)
        self.assertIn('Gap -0.6877.', note)
        self.assertNotIn('data-gap="0"', note)
        self.assertIn(
            'The USD/NOK gap is not a recommendation and is not copied into the ledger.',
            note,
        )
        self.assertEqual(
            response.body.count(
                'The USD/NOK gap is not a recommendation and is not copied into the ledger.'
            ),
            1,
        )
        self.assertIn('A match and a gap are not a ledger update.', note)
        self.assertEqual(response.body.count('A match and a gap are not a ledger update.'), 1)
        self.assertIn('The match is not a live source confirmation.', response.body)
        self.assertNotIn(
            'A row later than the selected date stays on the page. It was not dropped.',
            response.body,
        )
        self.assertIn(
            'data-observation="nb-exr-USD-NOK-2026-10-09" data-freshness="fresh"',
            response.body,
        )
        self.assertIn('data-observation="obs-usd-nok-2026-03-31"', response.body)
        self.assertEqual(self.state.ledger.value('2026-03-31'), before)
        self.assertEqual(before.known_subtotal, Decimal('24932.50'))
        rates = [row['rate'] for row, _posting in self.state.rate_postings]
        self.assertEqual(rates, ['10', '10.25'])
        self.assertNotIn('9.5623', rates)

    def test_shared_newest_usd_nok_date_uses_the_first_visible_row(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T08:03:34+00:00',
            (
                self._usd_row(
                    'nb-z-usd-nok-2026-10-09',
                    '9.10',
                    '2026-10-09',
                    ['recorded_fixture'],
                ),
                self._usd_row(
                    'nb-a-usd-nok-2026-10-09',
                    '9.70',
                    '2026-10-09',
                    ['live_retrieval'],
                ),
            ),
            (),
        )
        before = self.state.ledger.value('2026-03-31')
        response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(response.status, 200)
        note = self._ledger_section(response.body)
        self.assertIn('data-observation-id="nb-z-usd-nok-2026-10-09"', note)
        self.assertIn('data-stored-value="9.10"', note)
        self.assertIn('data-quality="recorded_fixture"', note)
        self.assertIn('data-multiple="true"', note)
        self.assertIn('data-equals="false"', note)
        self.assertIn('Newest stored observation 9.10.', note)
        self.assertIn('data-gap="-1.15"', note)
        self.assertIn('Gap -1.15.', note)
        self.assertNotIn('data-gap="-0.55"', note)
        self.assertNotIn('Newest stored observation 9.70.', note)
        self.assertNotIn('Newest stored observation 10.25.', note)
        self.assertIn('The date has more than one row.', note)
        self.assertIn('A match and a gap are not a ledger update.', note)
        self.assertIn('data-observation="nb-a-usd-nok-2026-10-09"', response.body)
        self.assertEqual(self.state.ledger.value('2026-03-31'), before)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def test_later_visible_conflict_date_is_the_newest_usd_nok(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T08:03:34+00:00',
            (
                self._usd_row(
                    'nb-exr-USD-NOK-shared',
                    '9.50',
                    '2026-10-08',
                    ['recorded_fixture'],
                    retrieval='2026-10-11',
                ),
                self._usd_row(
                    'nb-exr-USD-NOK-shared',
                    '9.20',
                    '2026-10-10',
                    ['recorded_fixture'],
                    retrieval='2026-10-12',
                ),
            ),
            (),
        )
        response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        self.assertEqual(response.status, 200)
        note = self._ledger_section(response.body)
        self.assertIn('data-observation-id="nb-exr-USD-NOK-shared"', note)
        self.assertIn('data-stored-value="9.20"', note)
        self.assertIn('data-observation-date="2026-10-10"', note)
        self.assertNotIn('data-multiple', note)
        self.assertNotIn('Newest stored observation 9.50.', note)
        self.assertNotIn('Newest stored observation 10.25.', note)
        self.assertIn('data-gap="-1.05"', note)
        self.assertIn('Gap -1.05.', note)
        self.assertNotIn('data-gap="0"', note)
        self.assertIn('A match and a gap are not a ledger update.', note)
        self.assertIn('Both observation dates stay visible: 2026-10-08, 2026-10-10.', response.body)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def test_scaled_stored_value_can_equal_the_ledger_rate(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T08:03:34+00:00',
            (self._usd_row(
                'nb-scaled-usd-nok',
                '10.250',
                '2026-04-01',
                ['recorded_fixture'],
                retrieval='2026-04-01',
            ),),
            (),
        )
        response = dispatch(self.state, 'GET', '/evidence?date=2026-04-01', None)
        self.assertEqual(response.status, 200)
        note = self._ledger_section(response.body)
        self.assertIn('data-stored-value="10.250"', note)
        self.assertIn('data-equals="true"', note)
        self.assertIn('Newest stored observation 10.250.', note)
        self.assertIn('The stored value equals 10.25.', note)
        self.assertIn('data-gap="0"', note)
        self.assertIn(
            'Gap 0. The USD/NOK gap is not a recommendation and is not copied into the ledger.',
            note,
        )
        self.assertNotIn('data-gap="0.000"', note)
        self.assertNotIn('Gap 0.000', note)
        self.assertIn('A match and a gap are not a ledger update.', note)
        self.assertEqual(response.body.count('A match and a gap are not a ledger update.'), 1)
        rates = [row['rate'] for row, _posting in self.state.rate_postings]
        self.assertEqual(rates, ['10', '10.25'])
        self.assertNotIn('10.250', rates)

    def test_missing_stored_usd_nok_does_not_equal_the_ledger_rate(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T08:03:34+00:00',
            (self._usd_row(
                'nb-missing-usd-nok',
                None,
                '2026-04-05',
                ['recorded_fixture'],
                retrieval='2026-04-05',
            ),),
            (),
        )
        response = dispatch(self.state, 'GET', '/evidence?date=2026-04-05', None)
        self.assertEqual(response.status, 200)
        note = self._ledger_section(response.body)
        self.assertIn('data-stored-value="missing"', note)
        self.assertIn('data-equals="false"', note)
        self.assertIn('Newest stored observation missing.', note)
        self.assertIn('The stored value does not equal 10.25.', note)
        self.assertIn('The stored value is missing.', note)
        self.assertIn('Ledger rate 10.25.', note)
        self.assertNotIn('data-gap', note)
        self.assertNotIn('Gap ', note)
        self.assertNotIn(
            'The USD/NOK gap is not a recommendation and is not copied into the ledger.',
            note,
        )
        self.assertIn('A match and a gap are not a ledger update.', note)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def test_no_visible_usd_nok_still_shows_the_ledger_rate(self):
        note = _usd_nok_ledger_section(())
        self.assertIn('No stored USD/NOK observation is visible.', note)
        self.assertIn('Ledger rate 10.25.', note)
        self.assertIn('data-ledger-rate="10.25"', note)
        self.assertIn('A match and a gap are not a ledger update.', note)
        self.assertNotIn('Newest stored observation', note)
        self.assertNotIn('data-stored-value', note)
        self.assertNotIn('data-gap', note)
        self.assertNotIn('Gap ', note)
        self.assertNotIn('The stored value is missing.', note)
        self.assertNotIn(
            'The USD/NOK gap is not a recommendation and is not copied into the ledger.',
            note,
        )
        policy = Observation(
            'obs-stale-policy',
            'norges-bank-open-data',
            'policy-rate',
            'percent',
            Decimal('4.50'),
            date(2026, 1, 2),
            date(2026, 1, 2),
            'synthetic-stale-policy-fixture',
            ('synthetic_fixture',),
        )
        policy_note = _usd_nok_ledger_section((policy,))
        self.assertIn('No stored USD/NOK observation is visible.', policy_note)
        self.assertIn('A match and a gap are not a ledger update.', policy_note)
        self.assertEqual(_future_kept_note((policy,), date(2026, 1, 2)), '')
        later = _future_kept_note((policy,), date(2026, 1, 1))
        self.assertEqual(
            later.count(
                'A row later than the selected date stays on the page. It was not dropped.'
            ),
            1,
        )

    def test_future_rows_stay_and_the_sentence_is_once(self):
        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T08:03:34+00:00',
            (
                self._usd_row(
                    'nb-future-obs',
                    '9.40',
                    '2026-04-02',
                    ['recorded_fixture'],
                    retrieval='2026-04-02',
                ),
                {
                    'observation_id': 'nb-future-retrieval',
                    'source_id': 'norges-bank-open-data',
                    'subject': 'policy-rate',
                    'unit': 'percent',
                    'value': '4.25',
                    'observation_time': '2026-03-31',
                    'retrieval_time': '2026-04-03',
                    'provenance': 'Norges Bank open data.',
                    'quality': ['recorded_fixture'],
                },
            ),
            (),
        )
        response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        self.assertEqual(response.status, 200)
        sentence = (
            'A row later than the selected date stays on the page. It was not dropped.'
        )
        self.assertEqual(response.body.count(sentence), 1)
        self.assertIn(
            'data-observation="nb-future-obs" '
            'data-freshness="future_observation future_retrieval"',
            response.body,
        )
        self.assertNotIn(
            'data-observation="nb-future-obs" data-freshness="fresh"',
            response.body,
        )
        self.assertIn(
            'data-observation="nb-future-retrieval" data-freshness="future_retrieval"',
            response.body,
        )
        self.assertNotIn(
            'data-observation="nb-future-retrieval" data-freshness="fresh"',
            response.body,
        )
        self.assertIn('The match is not a live source confirmation.', response.body)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def test_static_refresh_list_follows_the_request_order_without_fetching(self):
        from src.huginn_muninn.ingest.ecb import fetch_nok_eur
        from src.huginn_muninn.ingest.norges import (
            fetch_eur_nok,
            fetch_nowa,
            fetch_policy_rate,
            fetch_usd_nok,
        )
        from src.huginn_muninn.ingest.refresh import (
            CPI_REQUEST,
            REQUESTED_SERIES,
            _WINDOWED_REQUESTS,
            refresh_public,
        )
        import src.huginn_muninn.ingest.refresh as refresh_module
        import urllib.request

        self.assertEqual(
            tuple(name for name, _fetch in _WINDOWED_REQUESTS),
            REQUESTED_SERIES[:-1],
        )
        self.assertEqual(REQUESTED_SERIES[-1], CPI_REQUEST)
        self.assertEqual(
            tuple(fetch for _name, fetch in _WINDOWED_REQUESTS),
            (
                fetch_usd_nok,
                fetch_eur_nok,
                fetch_policy_rate,
                fetch_nowa,
                fetch_nok_eur,
            ),
        )
        self.assertEqual(
            REQUESTED_SERIES,
            (
                'Norges Bank USD/NOK',
                'Norges Bank EUR/NOK',
                'the policy rate',
                'NOWA',
                'ECB NOK/EUR',
                'the one Statistics Norway CPI cell for table 14700, 2026M07, total',
            ),
        )
        self.assertEqual(len(REQUESTED_SERIES), 6)
        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        original = refresh_module.refresh_public

        def refused(*args, **kwargs):
            raise AssertionError('refresh')

        refresh_module.refresh_public = refused
        try:
            response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        finally:
            refresh_module.refresh_public = original
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
        self.assertIs(original, refresh_public)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body.count('This list is not a refresh.'), 1)
        section = response.body.split('id="manual-refresh-list"', 1)[1].split('</section>', 1)[0]
        self.assertIn('This list is not a refresh.', section)
        listed = section.split('<ol>', 1)[1].split('</ol>', 1)[0]
        owners = (
            'norges-bank-open-data',
            'norges-bank-open-data',
            'norges-bank-open-data',
            'norges-bank-open-data',
            'ecb-sdw',
            'ssb-statbank',
        )
        self.assertEqual(
            listed,
            ''.join(
                f'<li data-source="{source}" data-due="due">{name}. due</li>'
                for name, source in zip(REQUESTED_SERIES, owners)
            ),
        )
        self.assertEqual(
            response.body.count('A later calendar day is not a scheduled refresh.'),
            1,
        )
        desk = (ROOT / 'src' / 'huginn_muninn' / 'desk.py').read_text(encoding='utf-8')
        self.assertNotIn('refresh_public', desk)
        self.assertNotIn('live_transport', desk)
        self.assertNotIn('add_rate', desk)
        self.assertNotIn('urllib', (ROOT / 'src' / 'huginn_muninn' / 'evidence.py').read_text(encoding='utf-8'))
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def _series_list(self, body):
        section = body.split('id="manual-refresh-list"', 1)[1].split('</section>', 1)[0]
        return section.split('<ol>', 1)[1].split('</ol>', 1)[0]

    def _cache_row(self, observation_id, source_id, subject, value, observed, retrieved):
        return {
            'observation_id': observation_id,
            'source_id': source_id,
            'subject': subject,
            'unit': 'recorded',
            'value': value,
            'observation_time': observed,
            'retrieval_time': retrieved,
            'provenance': 'recorded',
            'quality': ['recorded_fixture'],
        }

    def test_series_labels_follow_due_status_for_the_selected_date(self):
        import urllib.request
        from src.huginn_muninn.ingest.refresh import REQUESTED_SERIES

        sentence = 'A later calendar day is not a scheduled refresh.'
        owners = (
            'norges-bank-open-data',
            'norges-bank-open-data',
            'norges-bank-open-data',
            'norges-bank-open-data',
            'ecb-sdw',
            'ssb-statbank',
        )
        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        def labels_for(body, expected):
            listed = self._series_list(body)
            self.assertEqual(
                listed,
                ''.join(
                    f'<li data-source="{source}" data-due="{label}">{name}. {label}</li>'
                    for name, source, label in zip(REQUESTED_SERIES, owners, expected)
                ),
            )
            self.assertEqual(body.count(sentence), 1)
            self.assertNotIn('. overdue', listed)
            self.assertNotIn('. unknown', listed)

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        try:
            empty = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
            self.assertEqual(empty.status, 200)
            labels_for(empty.body, ('due',) * 6)
            self.assertIn('No live refresh has been stored.', empty.body)

            write_refresh(
                self.state.ingest_cache_dir,
                '2026-03-31T12:00:00+00:00',
                (self._cache_row(
                    'nb-stale-usd',
                    'norges-bank-open-data',
                    'USD/NOK',
                    '9.10',
                    '2026-01-02',
                    '2026-01-02',
                ),),
                (),
            )
            stale = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
            self.assertEqual(stale.status, 200)
            labels_for(stale.body, ('due',) * 6)
            self.assertIn('Last refresh 2026-03-31T12:00:00+00:00.', stale.body)
            self.assertIn(
                'data-source="norges-bank-open-data" data-posture="connected" data-due="due"',
                stale.body,
            )

            write_refresh(
                self.state.ingest_cache_dir,
                '2026-03-31T18:00:00+00:00',
                (
                    self._cache_row(
                        'nb-fresh-usd',
                        'norges-bank-open-data',
                        'USD/NOK',
                        '10.10',
                        '2026-03-31',
                        '2026-03-31',
                    ),
                    self._cache_row(
                        'ecb-fresh',
                        'ecb-sdw',
                        'EUR/NOK',
                        '11.10',
                        '2026-03-31',
                        '2026-03-31',
                    ),
                    self._cache_row(
                        'cpi-later',
                        'ssb-statbank',
                        'cpi-total',
                        '103.8',
                        '2026-07-01',
                        '2026-03-31',
                    ),
                ),
                (),
            )
            current = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
            self.assertEqual(current.status, 200)
            labels_for(
                current.body,
                ('current', 'current', 'current', 'current', 'current', 'due'),
            )
            self.assertIn('Last refresh 2026-03-31T18:00:00+00:00.', current.body)
            self.assertIn(
                'data-source="norges-bank-open-data" data-posture="connected" data-due="current"',
                current.body,
            )
            self.assertIn(
                'data-source="ecb-sdw" data-posture="connected" data-due="current"',
                current.body,
            )
            self.assertIn(
                'data-source="ssb-statbank" data-posture="connected" data-due="due"',
                current.body,
            )
        finally:
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def test_evidence_page_does_not_call_add_rate(self):
        source = (ROOT / 'src' / 'huginn_muninn' / 'desk.py').read_text(encoding='utf-8')
        self.assertNotIn('add_rate', source)
        self.assertIn('The match is not a live source confirmation.', source)
        self.assertIn('A match and a gap are not a ledger update.', source)
        self.assertIn(
            'The USD/NOK gap is not a recommendation and is not copied into the ledger.',
            source,
        )
        self.assertIn(
            'A row later than the selected date stays on the page. It was not dropped.',
            source,
        )
        self.assertIn('The policy rate and NOWA are not combined.', source)
        self.assertIn(
            'These hosts are the allowlist. This page does not open a connection.',
            source,
        )
        self.assertIn('A later calendar day is not a scheduled refresh.', source)
        self.assertNotIn('schedule.every', source)
        self.assertNotIn('BackgroundScheduler', source)

    def _rate_row(self, subject, value, observed, observation_id, retrieval=None):
        return Observation(
            observation_id,
            'norges-bank-open-data',
            subject,
            'percent',
            None if value is None else Decimal(value),
            date.fromisoformat(observed),
            date.fromisoformat(retrieval or observed),
            'recorded',
            ('recorded_fixture',),
        )

    def test_absent_policy_rate_and_nowa_say_they_are_not_visible(self):
        html = _policy_nowa_section(())
        self.assertEqual(html.count('The policy rate and NOWA are not combined.'), 1)
        self.assertIn('data-subject="policy-rate" data-visible="false"', html)
        self.assertIn('policy-rate is not visible.', html)
        self.assertIn('data-subject="nowa" data-visible="false"', html)
        self.assertIn('nowa is not visible.', html)
        self.assertNotIn('Latest observation date', html)
        self.assertNotIn('Value ', html)
        self.assertNotIn('The date has more than one row.', html)

    def test_shared_latest_date_shows_both_values_without_combining_them(self):
        rows = (
            self._rate_row('policy-rate', '4.50', '2026-01-02', 'policy-old'),
            self._rate_row('policy-rate', '4.25', '2026-10-08', 'policy-b', '2026-10-11'),
            self._rate_row('policy-rate', '4.00', '2026-10-08', 'policy-c', '2026-10-12'),
            self._rate_row('policy-rate', '3.00', '2026-10-07', 'policy-earlier'),
            self._rate_row('nowa', '4.40', '2026-10-08', 'nowa-e'),
            self._rate_row('nowa', '4.41', '2026-10-08', 'nowa-f'),
            self._rate_row('nowa', '4.10', '2026-10-07', 'nowa-older'),
            self._rate_row('USD/NOK', '9.5623', '2026-10-09', 'usd'),
        )
        html = _policy_nowa_section(rows)
        self.assertEqual(html.count('The policy rate and NOWA are not combined.'), 1)
        policy = html.split('data-subject="policy-rate"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-visible="true"', policy)
        self.assertIn('data-latest="2026-10-08"', policy)
        self.assertIn('data-values="4.25 4.00"', policy)
        self.assertIn('data-multiple="true"', policy)
        self.assertIn('Value 4.25.', policy)
        self.assertIn('Value 4.00.', policy)
        self.assertIn('The date has more than one row.', policy)
        self.assertNotIn('4.50', policy)
        self.assertNotIn('3.00', policy)
        self.assertNotIn('8.25', policy)
        self.assertNotIn('4.125', policy)
        nowa = html.split('data-subject="nowa"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-latest="2026-10-08"', nowa)
        self.assertIn('data-values="4.40 4.41"', nowa)
        self.assertIn('data-multiple="true"', nowa)
        self.assertIn('Value 4.40.', nowa)
        self.assertIn('Value 4.41.', nowa)
        self.assertIn('The date has more than one row.', nowa)
        self.assertNotIn('4.10', nowa)
        self.assertNotIn('8.81', nowa)
        self.assertNotIn('4.405', nowa)
        self.assertNotIn('8.65', html)
        self.assertNotIn('9.5623', html)
        self.assertNotIn('average', html.lower())

    def test_stored_nowa_is_shown_beside_the_policy_rate_without_a_fetch(self):
        import socket
        import urllib.request

        write_refresh(
            self.state.ingest_cache_dir,
            '2026-10-11T09:21:00+00:00',
            ({
                'observation_id': 'nb-short-NOWA-ON-R-2026-10-08',
                'source_id': 'norges-bank-open-data',
                'subject': 'nowa',
                'unit': 'percent',
                'value': '4.50',
                'observation_time': '2026-10-08',
                'retrieval_time': '2026-10-11',
                'provenance': 'recorded',
                'quality': ['recorded_fixture'],
            },),
            (),
        )
        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen
        socket_type = socket.socket

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        socket.socket = blocked
        try:
            response = dispatch(self.state, 'GET', '/evidence?date=2026-10-11', None)
        finally:
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
            socket.socket = socket_type
        self.assertEqual(response.status, 200)
        section = response.body.split('id="policy-nowa"', 1)[1].split('</section>', 1)[0]
        self.assertIn('The policy rate and NOWA are not combined.', section)
        policy = section.split('data-subject="policy-rate"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-latest="2026-01-02"', policy)
        self.assertIn('data-values="4.50"', policy)
        nowa = section.split('data-subject="nowa"', 1)[1].split('</p>', 1)[0]
        self.assertIn('data-visible="true"', nowa)
        self.assertIn('data-latest="2026-10-08"', nowa)
        self.assertIn('data-values="4.50"', nowa)
        self.assertIn('Value 4.50.', nowa)
        self.assertNotIn('The date has more than one row.', nowa)
        self.assertNotIn('9.00', section)
        self.assertNotIn('4.50', [
            row['rate'] for row, _posting in self.state.rate_postings
        ])
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )

    def test_allowlist_hosts_come_from_the_client_constant(self):
        import socket
        import urllib.request
        import src.huginn_muninn.ingest.client as client_module

        desk = (ROOT / 'src' / 'huginn_muninn' / 'desk.py').read_text(encoding='utf-8')
        self.assertIn(
            'from src.huginn_muninn.ingest.client import ALLOWLIST',
            desk,
        )
        for host in ALLOWLIST:
            self.assertNotIn(f"'{host}'", desk)
            self.assertNotIn(f'"{host}"', desk)
        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen
        socket_type = socket.socket
        fetch = client_module.Client.fetch
        live = client_module.live_transport

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        socket.socket = blocked
        client_module.Client.fetch = blocked
        client_module.live_transport = blocked
        try:
            response = dispatch(self.state, 'GET', '/evidence?date=2026-03-31', None)
        finally:
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
            socket.socket = socket_type
            client_module.Client.fetch = fetch
            client_module.live_transport = live
        self.assertEqual(response.status, 200)
        section = response.body.split('id="allowlist-hosts"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(
            section.count(
                'These hosts are the allowlist. This page does not open a connection.'
            ),
            1,
        )
        listed = section.split('<ul>', 1)[1].split('</ul>', 1)[0]
        self.assertEqual(
            listed,
            ''.join(f'<li>{host}</li>' for host in sorted(ALLOWLIST)),
        )
        self.assertNotIn('api.stlouisfed.org', section)
        self.assertNotIn('data.stlouisfed.org', section)
        self.assertNotIn('live_transport', desk)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )
