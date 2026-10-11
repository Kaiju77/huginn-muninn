import json
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from src.huginn_muninn.ledger import CashBalance, Deposit, Position, Withdrawal
from src.huginn_muninn.onboarding import (
    EnteredPortfolio,
    default_book_path,
    isin_is_valid,
)
from src.huginn_muninn.prototype import dispatch, open_state


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'fixtures' / 'synthetic_portfolio.json'
ENTERED_SENTENCE = (
    'This is your entered portfolio. Northline and Harbor on the other '
    'pages are a synthetic demo.'
)
SNAPSHOT_SENTENCE = (
    'Manual balances are snapshots. They are not a full performance record.'
)
QUANTITY_CONFLICT = (
    'This holding already has a quantity. A manual balance is not a '
    'second quantity.'
)
MANUAL_BALANCE_CONFLICT = (
    'This holding is a manual balance. A purchase would invent a quantity.'
)


def _visible(html):
    return re.sub(r'<[^>]*>', ' ', html)


class OnboardingTest(unittest.TestCase):
    def setUp(self):
        self._before_fixture = FIXTURE.read_bytes()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.overlay = root / 'synthetic-book.json'
        self.entered_path = root / 'book.json'
        self.state = open_state(ROOT, self.overlay, self.entered_path)
        self.book = self.state.entered

    def tearDown(self):
        self.assertEqual(FIXTURE.read_bytes(), self._before_fixture)
        self._tmp.cleanup()

    def test_empty_store_is_a_valid_book(self):
        self.assertEqual(self.book.load_error, '')
        self.assertEqual(self.book.reporting_currency, 'NOK')
        self.assertEqual(self.book.accounts, ())
        self.assertEqual(self.book.instruments, ())
        self.assertEqual(self.book.activities, ())
        self.assertEqual(self.book.manual_balances, ())
        self.assertFalse(self.entered_path.exists())
        self.assertEqual(
            default_book_path(ROOT),
            ROOT / 'var' / 'entered-portfolio' / 'book.json',
        )

    def test_valid_and_invalid_isin(self):
        self.assertTrue(isin_is_valid('US0378331005'))
        self.assertFalse(isin_is_valid('US0378331006'))
        self.assertFalse(isin_is_valid(''))
        self.assertFalse(isin_is_valid('US037833100'))
        saved = self.book.add_instrument(
            'Apple',
            'stock',
            'USD',
            'US0378331005',
        )
        self.assertTrue(saved.accepted)
        self.assertEqual(saved.identity, 'US0378331005')
        self.assertEqual(self.book.instruments[0]['origin'], 'entered')
        self.assertEqual(self.book.instruments[0]['isin'], 'US0378331005')
        self.assertEqual(self.book.instruments[0]['listing_currency'], 'USD')
        rejected = self.book.add_instrument(
            'Not Apple',
            'stock',
            'USD',
            'US0378331006',
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.message, 'That ISIN is not valid.')
        self.assertEqual(len(self.book.instruments), 1)
        duplicate = self.book.add_instrument(
            'Apple copy',
            'etf',
            'USD',
            'US0378331005',
        )
        self.assertFalse(duplicate.accepted)
        self.assertEqual(
            duplicate.message,
            'An instrument with this ISIN is already entered.',
        )
        self.assertEqual(len(self.book.instruments), 1)

    def test_blank_isin_stays_incomplete(self):
        saved = self.book.add_instrument('Local fund', 'fund', 'usd', '   ')
        self.assertTrue(saved.accepted)
        instrument = self.book.instruments[0]
        self.assertEqual(instrument['isin'], '')
        self.assertEqual(instrument['listing_currency'], 'usd')
        self.assertNotEqual(instrument['identity'], 'US0378331005')
        self.assertNotIn(instrument['identity'], instrument['display_name'])
        page = dispatch(self.state, 'GET', '/portfolio', None)
        self.assertIn('identification is incomplete', page.body)
        self.assertIn('fund', _visible(page.body))
        self.assertIn('usd', _visible(page.body))
        self.assertNotIn(instrument['identity'], _visible(page.body))

    def test_duplicate_account_is_rejected_in_plain_language(self):
        first = self.book.add_account('  DNB  ', ' Savings ')
        self.assertTrue(first.accepted)
        self.assertEqual(self.book.accounts[0]['institution'], 'DNB')
        self.assertEqual(self.book.accounts[0]['name'], 'Savings')
        self.assertEqual(self.book.accounts[0]['origin'], 'entered')
        again = self.book.add_account('DNB', 'Savings')
        self.assertFalse(again.accepted)
        self.assertEqual(
            again.message,
            'An account with this institution and name is already entered.',
        )
        self.assertEqual(len(self.book.accounts), 1)
        blank = self.book.add_account('   ', ' ')
        self.assertFalse(blank.accepted)
        self.assertEqual(
            blank.message,
            'Enter the institution and the account name.',
        )
        page = dispatch(self.state, 'GET', '/portfolio', None)
        visible = _visible(page.body)
        self.assertIn('DNB', visible)
        self.assertIn('Savings', visible)
        self.assertNotIn(first.identity, visible)

    def test_activity_rejects_missing_date_provenance_and_bad_amounts(self):
        account = self.book.add_account('Bank', 'Main').identity
        missing_date = self.book.add_activity(
            'contribution',
            account,
            '',
            'payroll',
            currency='NOK',
            amount='10',
        )
        self.assertFalse(missing_date.accepted)
        self.assertEqual(missing_date.message, 'Enter the date.')
        self.assertEqual(self.book.activities, ())
        blank_source = self.book.add_activity(
            'contribution',
            account,
            '2026-01-01',
            '   ',
            currency='NOK',
            amount='10',
        )
        self.assertFalse(blank_source.accepted)
        self.assertEqual(blank_source.message, 'Say where this came from.')
        self.assertIn('blank_provenance', blank_source.reasons)
        not_decimal = self.book.add_activity(
            'contribution',
            account,
            '2026-01-01',
            'payroll',
            currency='NOK',
            amount='abc',
        )
        self.assertFalse(not_decimal.accepted)
        self.assertEqual(
            not_decimal.message,
            'The amount must be a decimal number.',
        )
        self.assertIn('non_decimal', not_decimal.reasons)
        not_finite = self.book.add_activity(
            'contribution',
            account,
            '2026-01-01',
            'payroll',
            currency='NOK',
            amount='NaN',
        )
        self.assertFalse(not_finite.accepted)
        self.assertEqual(
            not_finite.message,
            'The amount must be a finite number.',
        )
        self.assertIn('non_finite', not_finite.reasons)
        self.assertNotIn('non_finite', not_finite.message)
        self.assertEqual(self.book.activities, ())
        stored = json.loads(self.entered_path.read_text(encoding='utf-8'))
        self.assertEqual(stored['activities'], [])

    def test_fee_reduces_cash_and_is_labeled_fee(self):
        account = self.book.add_account('Bank', 'Main').identity
        opened = self.book.add_activity(
            'contribution',
            account,
            '2026-01-01',
            'payroll',
            currency='NOK',
            amount='100',
        )
        self.assertTrue(opened.accepted)
        fee = self.book.add_activity(
            'fee',
            account,
            '2026-01-02',
            'custody invoice',
            currency='NOK',
            amount='15',
        )
        self.assertTrue(fee.accepted)
        self.assertEqual(self.book.activities[-1]['activity'], 'fee')
        self.assertEqual(self.book.activities[-1]['origin'], 'entered')
        self.assertEqual(
            self.book.books().cash,
            (CashBalance(account, 'NOK', Decimal('85')),),
        )
        self.assertIsInstance(self.book.recorded_events()[-1], Withdrawal)
        self.assertIsInstance(self.book.recorded_events()[0], Deposit)
        page = dispatch(self.state, 'GET', '/portfolio', None)
        row = page.body.split('data-activity="fee"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('>Fee<', row)
        self.assertNotIn('withdrawal', row.lower())
        self.assertIn('>85<', page.body)
        self.assertNotIn('Withdrawal', _visible(page.body))
        self.assertNotIn('Deposit', _visible(page.body))

    def test_purchase_then_manual_balance_is_rejected(self):
        account = self.book.add_account('Bank', 'Main').identity
        self.book.add_instrument('Apple', 'stock', 'USD', 'US0378331005')
        self.book.add_activity(
            'contribution',
            account,
            '2026-01-01',
            'wire',
            currency='USD',
            amount='500',
        )
        purchase = self.book.add_activity(
            'purchase',
            account,
            '2026-01-02',
            'ticket',
            instrument='US0378331005',
            quantity='2',
            cash_currency='USD',
            cash_amount='100',
            fee='0',
        )
        self.assertTrue(purchase.accepted)
        rejected = self.book.add_manual_balance(
            account,
            'US0378331005',
            '2',
            'USD',
            '2026-01-03',
            'statement',
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.message, QUANTITY_CONFLICT)
        self.assertEqual(self.book.manual_balances, ())
        self.assertEqual(
            self.book.books().positions,
            (Position(account, 'US0378331005', Decimal('2')),),
        )
        page = dispatch(
            self.state,
            'POST',
            '/portfolio',
            {
                'action': 'activity',
                'activity': 'manual balance',
                'account': account,
                'balance_subject': 'US0378331005',
                'amount': '2',
                'currency': 'USD',
                'event_date': '2026-01-03',
                'provenance': 'statement',
            },
        )
        self.assertEqual(page.status, 400)
        self.assertIn(QUANTITY_CONFLICT, page.body)
        self.assertEqual(self.book.manual_balances, ())

    def test_manual_balance_then_purchase_is_rejected(self):
        account = self.book.add_account('Bank', 'Main').identity
        self.book.add_instrument('Apple', 'stock', 'USD', 'US0378331005')
        self.book.add_activity(
            'contribution',
            account,
            '2026-01-01',
            'wire',
            currency='USD',
            amount='500',
        )
        balance = self.book.add_manual_balance(
            account,
            'US0378331005',
            '10',
            'USD',
            '2026-01-02',
            'statement',
        )
        self.assertTrue(balance.accepted)
        rejected = self.book.add_activity(
            'purchase',
            account,
            '2026-01-03',
            'ticket',
            instrument='US0378331005',
            quantity='1',
            cash_currency='USD',
            cash_amount='40',
            fee='0',
        )
        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.message, MANUAL_BALANCE_CONFLICT)
        self.assertEqual(
            [row['activity'] for row in self.book.activities],
            ['contribution'],
        )
        self.assertEqual(self.book.books().positions, ())
        self.assertIsInstance(self.book.recorded_events()[0], Deposit)
        page = dispatch(
            self.state,
            'POST',
            '/portfolio',
            {
                'action': 'activity',
                'activity': 'purchase',
                'account': account,
                'instrument': 'US0378331005',
                'event_date': '2026-01-04',
                'provenance': 'ticket',
                'quantity': '1',
                'cash_currency': 'USD',
                'cash_amount': '40',
                'fee': '0',
            },
        )
        self.assertEqual(page.status, 400)
        self.assertIn(MANUAL_BALANCE_CONFLICT, page.body)
        self.assertEqual(len(self.book.activities), 1)

    def test_synthetic_fixture_is_not_the_entered_book(self):
        before = FIXTURE.read_bytes()
        foreign = EnteredPortfolio(FIXTURE)
        self.assertNotEqual(foreign.load_error, '')
        self.assertEqual(foreign.accounts, ())
        self.assertEqual(foreign.instruments, ())
        self.assertEqual(FIXTURE.read_bytes(), before)
        account = self.book.add_account('Bank', 'Main').identity
        self.book.add_activity(
            'contribution',
            account,
            '2026-05-01',
            'transfer',
            currency='NOK',
            amount='20',
        )
        stored = json.loads(self.entered_path.read_text(encoding='utf-8'))
        text = self.entered_path.read_text(encoding='utf-8')
        self.assertEqual(stored['origin'], 'entered')
        self.assertEqual(stored['reporting_currency'], 'NOK')
        self.assertNotIn('prices', stored)
        self.assertNotIn('rates', stored)
        self.assertNotIn('events', stored)
        self.assertNotIn('Northline', text)
        self.assertNotIn('Harbor', text)
        self.assertNotIn('northline', text)
        self.assertNotIn('harbor', text)
        self.assertNotIn('brokerage', text)
        self.assertEqual(FIXTURE.read_bytes(), before)
        page = dispatch(self.state, 'GET', '/portfolio', None)
        self.assertIn(ENTERED_SENTENCE, page.body)
        rest = page.body.replace(ENTERED_SENTENCE, '')
        self.assertNotIn('Northline', rest)
        self.assertNotIn('Harbor', rest)
        self.assertNotIn('15050', page.body)
        self.assertNotIn('These figures are synthetic', page.body)
        ledger = dispatch(self.state, 'GET', '/ledger', None)
        self.assertIn('15050', ledger.body)
        self.assertIn('These figures are synthetic', ledger.body)
        self.assertEqual(
            self.state.ledger.books('2026-03-20').cash[0].amount,
            Decimal('15050'),
        )

    def test_foreign_usd_cash_stays_usd(self):
        account = self.book.add_account('Bank', 'Main').identity
        contribution = self.book.add_activity(
            'contribution',
            account,
            '2026-02-01',
            'wire',
            currency='USD',
            amount='40',
        )
        self.assertTrue(contribution.accepted)
        balance = self.book.add_manual_balance(
            account,
            'cash',
            '12',
            'USD',
            '2026-02-02',
            'statement',
        )
        self.assertTrue(balance.accepted)
        self.assertEqual(
            self.book.books().cash,
            (CashBalance(account, 'USD', Decimal('40')),),
        )
        self.assertEqual(self.book.books().positions, ())
        self.assertEqual(self.book.manual_balances[0]['currency'], 'USD')
        self.assertEqual(self.book.manual_balances[0]['amount'], '12')
        self.assertEqual(self.book.manual_balances[0]['holding'], 'cash')
        ledger = self.book.ledger()
        self.assertEqual(ledger._prices, [])
        self.assertEqual(ledger._rates, [])
        page = dispatch(self.state, 'GET', '/portfolio', None)
        row = page.body.split('data-currency="USD"', 1)[1].split('</tr>', 1)[0]
        self.assertIn('USD', row)
        self.assertIn('40', row)
        self.assertNotIn('NOK', row)
        self.assertNotIn('10.25', page.body)
        self.assertNotIn('missing_rate', page.body)
        self.assertIn(SNAPSHOT_SENTENCE, page.body)
        self.assertIn('Foreign currency stays in its own currency.', page.body)
        source = Path(
            ROOT / 'src' / 'huginn_muninn' / 'onboarding.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn('add_price', source)
        self.assertNotIn('add_rate', source)
        self.assertNotIn('synthetic_portfolio', source)

    def test_dividend_without_a_holding_is_a_sentence(self):
        account = self.book.add_account('Bank', 'Main').identity
        self.book.add_instrument('Apple', 'stock', 'USD', 'US0378331005')
        page = dispatch(
            self.state,
            'POST',
            '/portfolio',
            {
                'action': 'activity',
                'activity': 'dividend',
                'account': account,
                'instrument': 'US0378331005',
                'event_date': '2026-03-01',
                'provenance': 'fund notice',
                'currency': 'USD',
                'amount': '3',
            },
        )
        self.assertEqual(page.status, 400)
        self.assertIn('data-reason="no_position"', page.body)
        self.assertIn('A dividend needs an existing holding.', page.body)
        self.assertNotIn('no_position', _visible(page.body))
        self.assertEqual(self.book.activities, ())

    def test_get_portfolio_does_not_fetch(self):
        import socket
        import urllib.request

        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen
        socket_type = socket.socket

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        socket.socket = blocked
        try:
            response = dispatch(self.state, 'GET', '/portfolio', None)
        finally:
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
            socket.socket = socket_type
        self.assertEqual(response.status, 200)
        self.assertIn('text/html', response.content_type)
        self.assertIn(ENTERED_SENTENCE, response.body)
        self.assertIn(SNAPSHOT_SENTENCE, response.body)
        self.assertFalse(self.entered_path.exists())

    def test_reset_keeps_the_entered_book(self):
        self.book.add_account('Bank', 'Main')
        entered_before = self.entered_path.read_bytes()
        posted = dispatch(
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
        self.assertEqual(posted.status, 200)
        self.assertTrue(self.overlay.is_file())
        reset = dispatch(self.state, 'POST', '/reset', {})
        self.assertEqual(reset.status, 200)
        self.assertFalse(self.overlay.is_file())
        self.assertEqual(self.entered_path.read_bytes(), entered_before)
        reloaded = EnteredPortfolio(self.entered_path)
        self.assertEqual(reloaded.accounts[0]['name'], 'Main')
        self.assertEqual(reloaded.load_error, '')
        ledger = dispatch(self.state, 'GET', '/ledger', None)
        self.assertEqual(ledger.status, 200)
        self.assertIn('15050', ledger.body)
        self.assertIn('These figures are synthetic', ledger.body)
        self.assertIn('synthetic', ledger.body.lower())
