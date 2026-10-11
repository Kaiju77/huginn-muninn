import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.huginn_muninn.desk import INTELLIGENCE
from src.huginn_muninn.evidence import (
    MAX_AGE_DAYS,
    EvidenceStore,
    assess,
    due_status,
    freshness_flags,
    load_registry,
    open_evidence,
    source_posture,
    visible_observations,
)
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
        self.assertEqual(source_posture(sources['ssb-statbank']), 'prepared')
        self.assertEqual(source_posture(sources['sec-edgar-public']), 'prepared')
        self.assertEqual(source_posture(sources['fred']), 'blocked')
        self.assertEqual(source_posture(sources['social-unverified']), 'excluded')
        self.assertIs(sources['norges-bank-open-data']['live_fetch'], True)
        self.assertIs(sources['ecb-sdw']['live_fetch'], True)
        self.assertIs(sources['ssb-statbank']['live_fetch'], False)
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
        self.assertNotIn('ssb-statbank', statuses)
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
        self.assertIn('data-source="ssb-statbank" data-posture="prepared"', body)
        self.assertIn('data-source="sec-edgar-public" data-posture="prepared"', body)
        self.assertIn('data-source="fred" data-posture="blocked"', body)
        self.assertIn('data-source="social-unverified" data-posture="excluded"', body)
        self.assertEqual(body.count('live_fetch false'), 4)
        self.assertEqual(body.count('live_fetch true'), 2)
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
        self.assertIn(
            'data-observation="obs-stale-policy" data-freshness="fresh"',
            selected.body,
        )
        self.assertIn(
            'data-observation="obs-usd-nok-2026-03-31" '
            'data-freshness="future_observation future_retrieval"',
            selected.body,
        )
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
