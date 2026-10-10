import importlib.util
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.huginn_muninn.ledger import CashBalance, Position
from src.huginn_muninn.prototype import dispatch, load_document, open_state


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'fixtures' / 'synthetic_portfolio.json'


def _line(valuation, identity):
    matches = [line for line in valuation.lines if line.identity == identity]
    if len(matches) != 1:
        raise AssertionError(valuation.lines)
    return matches[0]


def _load_server():
    script_path = ROOT / 'scripts' / 'serve_prototype.py'
    spec = importlib.util.spec_from_file_location('serve_prototype', script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {script_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrototypeFixtureTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.overlay = Path(self._tmp.name) / 'synthetic-book.json'
        self.state = open_state(ROOT, self.overlay)

    def tearDown(self):
        self._tmp.cleanup()

    def test_fixture_locked_books_and_valuations(self):
        ledger = self.state.ledger
        opened = ledger.books('2026-01-15')
        self.assertEqual(
            opened.cash,
            (CashBalance('brokerage', 'NOK', Decimal('25000')),),
        )
        self.assertEqual(opened.positions, ())
        opened_value = ledger.value('2026-01-15')
        self.assertTrue(opened_value.complete)
        self.assertEqual(opened_value.known_subtotal, Decimal('25000'))

        bought = ledger.books('2026-01-16')
        self.assertEqual(bought.cash[0].amount, Decimal('14985'))
        self.assertEqual(
            bought.positions,
            (Position('brokerage', 'northline', Decimal('20')),),
        )
        bought_value = ledger.value('2026-01-16')
        self.assertTrue(bought_value.complete)
        self.assertEqual(bought_value.known_subtotal, Decimal('24985'))

        harbor_day = ledger.books('2026-02-18')
        self.assertEqual(harbor_day.cash[0].amount, Decimal('14260'))
        self.assertEqual(
            harbor_day.positions,
            (
                Position('brokerage', 'northline', Decimal('20')),
                Position('brokerage', 'harbor', Decimal('5')),
            ),
        )
        harbor_value = ledger.value('2026-02-18')
        self.assertTrue(harbor_value.complete)
        self.assertEqual(harbor_value.known_subtotal, Decimal('25335'))

        march_books = ledger.books('2026-03-10')
        self.assertEqual(march_books.cash[0].amount, Decimal('16550'))
        self.assertEqual(march_books.positions[0].quantity, Decimal('16'))
        self.assertEqual(march_books.positions[1].quantity, Decimal('5'))
        march = ledger.value('2026-03-10')
        self.assertFalse(march.complete)
        self.assertEqual(march.known_subtotal, Decimal('25750'))
        harbor = _line(march, 'harbor')
        self.assertEqual(harbor.reasons, ('missing_rate',))
        self.assertIsNone(harbor.reporting_amount)
        self.assertEqual(harbor.price_id, 'px-harbor-0310')
        self.assertIsNone(harbor.rate_id)

        later = ledger.books('2026-03-20')
        self.assertEqual(later.cash[0].amount, Decimal('15050'))
        self.assertEqual(
            later.positions,
            (
                Position('brokerage', 'northline', Decimal('16')),
                Position('brokerage', 'harbor', Decimal('5')),
            ),
        )

        close = ledger.value('2026-03-31')
        self.assertTrue(close.complete)
        self.assertEqual(close.known_subtotal, Decimal('24932.50'))
        northline = _line(close, 'northline')
        harbor_close = _line(close, 'harbor')
        self.assertEqual(northline.price_id, 'px-northline-0331')
        self.assertIsNone(northline.rate_id)
        self.assertEqual(harbor_close.price_id, 'px-harbor-0331')
        self.assertEqual(harbor_close.rate_id, 'fx-0331')

    def test_home_shows_latest_cash_and_synthetic_warning(self):
        response = dispatch(self.state, 'GET', '/', None)
        self.assertEqual(response.status, 200)
        self.assertIn('text/html', response.content_type)
        self.assertIn('15050', response.body)
        self.assertIn('synthetic', response.body.lower())
        self.assertIn('not a recommendation', response.body.lower())

    def test_posted_deposit_updates_books_through_a_temporary_overlay(self):
        before_fixture = FIXTURE.read_text(encoding='utf-8')
        developer_overlay = ROOT / 'var' / 'synthetic-book.json'
        developer_overlay_existed = developer_overlay.exists()
        response = dispatch(
            self.state,
            'POST',
            '/transactions',
            {
                'type': 'deposit',
                'event_id': 'dep-added',
                'account': 'brokerage',
                'currency': 'NOK',
                'amount': '100',
                'event_date': '2026-04-01',
                'provenance': 'synthetic-added-deposit',
            },
        )
        self.assertEqual(response.status, 200)
        self.assertIn('accepted', response.body.lower())
        books = self.state.ledger.books('2026-04-01')
        self.assertEqual(books.cash[0].amount, Decimal('15150'))
        self.assertTrue(self.overlay.is_file())
        self.assertEqual(self.overlay.parent, Path(self._tmp.name))
        reloaded = open_state(ROOT, self.overlay)
        self.assertEqual(
            reloaded.ledger.books('2026-04-01').cash[0].amount,
            Decimal('15150'),
        )
        self.assertEqual(FIXTURE.read_text(encoding='utf-8'), before_fixture)
        self.assertEqual(developer_overlay.exists(), developer_overlay_existed)

    def test_infinity_amount_is_rejected_and_books_stay_put(self):
        before = self.state.ledger.books('2026-04-01')
        response = dispatch(
            self.state,
            'POST',
            '/transactions',
            {
                'type': 'deposit',
                'event_id': 'dep-infinity',
                'account': 'brokerage',
                'currency': 'NOK',
                'amount': 'Infinity',
                'event_date': '2026-04-01',
                'provenance': 'synthetic-infinity',
            },
        )
        self.assertIn('non_finite', response.body)
        self.assertEqual(self.state.ledger.books('2026-04-01'), before)
        reloaded = open_state(ROOT, self.overlay)
        self.assertEqual(reloaded.ledger.books('2026-04-01'), before)
        self.assertIn('non_finite', reloaded.event_postings[-1][1].reasons)

    def test_space_provenance_is_blank_provenance(self):
        before = self.state.ledger.books('2026-04-01')
        response = dispatch(
            self.state,
            'POST',
            '/transactions',
            {
                'type': 'deposit',
                'event_id': 'dep-blank',
                'account': 'brokerage',
                'currency': 'NOK',
                'amount': '100',
                'event_date': '2026-04-01',
                'provenance': '   ',
            },
        )
        self.assertIn('blank_provenance', response.body)
        self.assertEqual(self.state.ledger.books('2026-04-01'), before)

    def test_incomplete_valuation_leaves_harbor_reporting_blank(self):
        response = dispatch(self.state, 'GET', '/valuation?date=2026-03-10', None)
        self.assertEqual(response.status, 200)
        self.assertIn('missing_rate', response.body)
        self.assertIn('known subtotal', response.body.lower())
        self.assertIn('not complete', response.body.lower())
        start = response.body.index('data-identity="harbor"')
        tag_end = response.body.index('>', start)
        chunk = response.body[start:tag_end]
        self.assertIn('data-reporting=""', chunk)
        self.assertNotIn('data-reporting="0"', chunk)
        row = response.body[start:response.body.index('</tr>', start)]
        self.assertNotIn('>0<', row)

    def test_reconcile_shows_match_and_mismatch(self):
        response = dispatch(self.state, 'GET', '/reconcile', None)
        self.assertEqual(response.status, 200)
        self.assertIn('stmt-match', response.body)
        self.assertIn('15051', response.body)
        self.assertIn('amount_mismatch', response.body)
        self.assertIn('duplicate_statement_row', response.body)

    def test_chart_uses_value_results_and_marks_incomplete_dates(self):
        response = dispatch(self.state, 'GET', '/chart', None)
        body = response.body
        self.assertEqual(response.status, 200)
        self.assertIn('<svg', body)
        self.assertEqual(body.lower().count('<svg'), 1)
        self.assertIn('2026-03-10', body)
        self.assertIn('known subtotal', body.lower())
        self.assertNotIn('portfolio value', body.lower())
        self.assertNotIn('<img', body.lower())
        self.assertNotIn('@font-face', body.lower())
        self.assertNotIn('url(', body.lower())
        for day in self.state.observation_dates():
            valuation = self.state.ledger.value(day)
            self.assertIn(f'data-date="{day}"', body)
            self.assertIn(format(valuation.known_subtotal, 'f'), body)
        self.assertRegex(
            body,
            r'data-date="2026-03-10"[^>]*data-complete="false"',
        )
        self.assertNotIn('data-date="2026-03-11"', body)
        self.assertNotIn('data-date="2026-01-17"', body)

    def test_invalid_history_date_shows_the_ledger_error(self):
        response = dispatch(self.state, 'GET', '/history?date=2026-02-31', None)
        self.assertEqual(response.status, 400)
        self.assertIn('invalid_date', response.body)

    def test_reset_deletes_only_the_overlay(self):
        dispatch(
            self.state,
            'POST',
            '/transactions',
            {
                'type': 'deposit',
                'event_id': 'dep-reset',
                'account': 'brokerage',
                'currency': 'NOK',
                'amount': '100',
                'event_date': '2026-04-01',
                'provenance': 'synthetic-reset',
            },
        )
        self.assertTrue(self.overlay.is_file())
        response = dispatch(self.state, 'POST', '/reset', {})
        self.assertEqual(response.status, 200)
        self.assertFalse(self.overlay.exists())
        self.assertTrue(self.state.fixture_path.is_file())
        self.assertEqual(
            self.state.ledger.books('2026-03-20').cash[0].amount,
            Decimal('15050'),
        )

    def test_loader_rejects_a_json_numeric_amount(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_path = Path(tmp) / 'numeric.json'
            document = json.loads(FIXTURE.read_text(encoding='utf-8'))
            document['events'][0]['amount'] = 25000
            copy_path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_document(copy_path)
        self.assertIn('"25000"', FIXTURE.read_text(encoding='utf-8'))

    def test_server_refuses_a_non_loopback_bind(self):
        module = _load_server()
        host, port = module.resolve_bind(['serve_prototype.py'])
        self.assertEqual(host, '127.0.0.1')
        self.assertEqual(port, 8765)
        with self.assertRaises(SystemExit) as raised:
            module.resolve_bind(['serve_prototype.py', '--bind', '0.0.0.0'])
        self.assertIn('non-loopback', str(raised.exception))
