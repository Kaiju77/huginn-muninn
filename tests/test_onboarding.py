import json
import re
import tempfile
import unittest
from decimal import Context, Decimal, localcontext
from pathlib import Path

from src.huginn_muninn.ledger import CashBalance, Deposit, Position, Withdrawal
from src.huginn_muninn.onboarding import (
    CASH_SNAPSHOT_NOT_ADDED,
    NO_SNAPSHOT,
    PRICE_CURRENCY_MISMATCH,
    EnteredPortfolio,
    default_book_path,
    isin_is_valid,
    price_freshness,
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


VALUATION_SENTENCE = 'This valuation is not a recommendation.'
MISSING_PRICE_SENTENCE = 'A missing price stays unknown.'
SNAPSHOT_VALUE_SENTENCE = (
    'A manual balance is a snapshot on its date. It is not a price and '
    'it is not a full performance record.'
)


def _value_row(html, kind, identity):
    section = html.split('<h2>Historical value</h2>', 1)[0]
    for part in section.split('<tr')[1:]:
        row = part.split('</tr>', 1)[0]
        if f'data-kind="{kind}"' not in row:
            continue
        if 'data-known="' not in row:
            continue
        if f'data-identity="{identity}"' not in row:
            continue
        return row
    return ''


class EnteredValuationTest(unittest.TestCase):
    def setUp(self):
        self._before_fixture = FIXTURE.read_bytes()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.overlay = root / 'synthetic-book.json'
        self.entered_path = root / 'book.json'
        self.state = open_state(ROOT, self.overlay, self.entered_path)
        self.book = self.state.entered
        self._price_postings = list(self.state.price_postings)
        self._rate_postings = list(self.state.rate_postings)

    def tearDown(self):
        self.assertEqual(FIXTURE.read_bytes(), self._before_fixture)
        self._tmp.cleanup()

    def _account(self):
        return self.book.add_account('Bank', 'Main').identity

    def _fund(self, currency='NOK'):
        saved = self.book.add_instrument('Local fund', 'fund', currency)
        self.assertTrue(saved.accepted)
        return saved.identity

    def _contribute(self, account, day, amount, currency='NOK'):
        saved = self.book.add_activity(
            'contribution',
            account,
            day,
            'transfer',
            currency=currency,
            amount=amount,
        )
        self.assertTrue(saved.accepted)

    def _buy(self, account, instrument, day, quantity, cash):
        saved = self.book.add_activity(
            'purchase',
            account,
            day,
            'ticket',
            instrument=instrument,
            quantity=quantity,
            cash_currency='NOK',
            cash_amount=cash,
            fee='0',
        )
        self.assertTrue(saved.accepted)

    def _price(self, instrument, amount, currency, valuation, evidence='same'):
        if evidence == 'same':
            evidence = valuation
        saved = self.book.record_price(
            instrument,
            amount,
            currency,
            valuation,
            evidence,
            'statement',
        )
        self.assertTrue(saved.accepted, saved.message)
        return saved

    def test_price_requires_every_field_and_matching_currency(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '100')
        instrument = self._fund('NOK')
        self._buy(account, instrument, '2026-01-02', '2', '40')
        before = self.book.books()
        blank = self.book.record_price('', '', '', '', '', '')
        self.assertFalse(blank.accepted)
        self.assertIn('Choose an instrument that you have entered.', blank.message)
        self.assertIn('Enter the amount.', blank.message)
        self.assertIn('Enter the currency.', blank.message)
        self.assertIn('Enter the valuation date.', blank.message)
        self.assertIn('Enter the evidence date.', blank.message)
        self.assertIn('Say where this came from.', blank.message)
        self.assertEqual(self.book.prices, ())
        mismatch = self.book.record_price(
            instrument,
            '4',
            'EUR',
            '2026-01-02',
            '2026-01-02',
            'statement',
        )
        self.assertFalse(mismatch.accepted)
        self.assertEqual(mismatch.message, PRICE_CURRENCY_MISMATCH)
        self.assertIn('currency_mismatch', mismatch.reasons)
        self.assertNotIn('currency_mismatch', mismatch.message)
        self.assertEqual(self.book.prices, ())
        case = self.book.record_price(
            instrument,
            '4',
            'nok',
            '2026-01-02',
            '2026-01-02',
            'statement',
        )
        self.assertFalse(case.accepted)
        self.assertEqual(case.message, PRICE_CURRENCY_MISMATCH)
        negative = self.book.record_price(
            instrument,
            '-1',
            'NOK',
            '2026-01-02',
            '2026-01-02',
            'statement',
        )
        self.assertFalse(negative.accepted)
        self.assertIn('The amount cannot be negative.', negative.message)
        self.assertEqual(before.positions, self.book.books().positions)
        self.assertEqual(before.cash, self.book.books().cash)
        self.assertEqual(self.book.manual_balances, ())
        self.assertEqual(len(self.book.activities), 2)

    def test_zero_price_is_known_and_a_missing_price_is_not_zero(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '100')
        instrument = self._fund()
        self._buy(account, instrument, '2026-01-02', '2', '40')
        missing = self.book.value_on('2026-01-02')
        row = [
            line for line in missing.lines
            if line.kind == 'quantity'
        ][0]
        self.assertFalse(row.known)
        self.assertIsNone(row.amount)
        self.assertNotEqual(row.amount, Decimal(0))
        posted = dispatch(
            self.state,
            'POST',
            '/portfolio/valuation',
            {
                'action': 'price',
                'instrument': instrument,
                'amount': '0',
                'currency': 'NOK',
                'valuation_date': '2026-01-02',
                'evidence_date': '2026-01-02',
                'provenance': 'statement',
                'date': '2026-01-02',
            },
        )
        self.assertEqual(posted.status, 200)
        self.assertEqual(self.book.prices[0]['amount'], '0')
        self.assertEqual(self.book.prices[0]['origin'], 'entered')
        valued = self.book.value_on('2026-01-02')
        quantity = [
            line for line in valued.lines
            if line.kind == 'quantity'
        ][0]
        self.assertTrue(quantity.known)
        self.assertEqual(quantity.amount, Decimal(0))
        self.assertIsInstance(quantity.amount, Decimal)
        self.assertEqual(quantity.freshness, 'fresh')
        page_row = _value_row(posted.body, 'quantity', instrument)
        self.assertIn('data-amount="0"', page_row)
        self.assertIn('data-known="true"', page_row)
        reloaded = EnteredPortfolio(self.entered_path)
        self.assertEqual(reloaded.prices[0]['currency'], 'NOK')
        self.assertEqual(self.book.books().positions[0].quantity, Decimal('2'))
        self.assertEqual(self.book.ledger()._prices, [])
        self.assertEqual(self.book.ledger()._rates, [])

    def test_two_prices_on_one_date_are_ambiguous_and_another_date_is_unused(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '100')
        instrument = self._fund()
        self._buy(account, instrument, '2026-01-02', '2', '40')
        self._price(instrument, '3', 'NOK', '2026-01-02')
        self._price(instrument, '5', 'NOK', '2026-01-02')
        self._price(instrument, '9', 'NOK', '2026-01-08')
        self.assertEqual(len(self.book.prices), 3)
        report = self.book.value_on('2026-01-02')
        quantity = [
            line for line in report.lines
            if line.kind == 'quantity'
        ][0]
        self.assertFalse(quantity.known)
        self.assertIsNone(quantity.amount)
        self.assertEqual(quantity.detail, 'The price is ambiguous.')
        self.assertNotEqual(quantity.amount, Decimal('6'))
        self.assertNotEqual(quantity.amount, Decimal('10'))
        later = self.book.value_on('2026-01-05')
        later_quantity = [
            line for line in later.lines
            if line.kind == 'quantity'
        ][0]
        self.assertFalse(later_quantity.known)
        self.assertIsNone(later_quantity.amount)
        self.assertEqual(
            price_freshness('2026-01-01', '2026-01-01', '2026-01-08'),
            ('fresh',),
        )
        self.assertEqual(
            price_freshness('2026-01-01', '2026-01-01', '2026-01-09'),
            ('stale',),
        )

    def test_a_stale_price_stays_the_price_for_its_date(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '100')
        instrument = self._fund()
        self._buy(account, instrument, '2026-01-02', '2', '40')
        self._price(instrument, '4', 'NOK', '2026-01-02')
        on_date = self.book.value_on('2026-01-02')
        quantity = [line for line in on_date.lines if line.kind == 'quantity'][0]
        self.assertEqual(quantity.amount, Decimal('8'))
        self.assertEqual(quantity.freshness, 'fresh')
        later = self.book.value_on('2026-01-12')
        missed = [line for line in later.lines if line.kind == 'quantity'][0]
        self.assertIsNone(missed.amount)
        self.assertEqual(len(self.book.prices), 1)
        page = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-01-12',
            None,
        )
        self.assertIn('data-freshness="stale"', page.body)
        self._price(instrument, '9', 'NOK', '2026-01-12')
        self.assertEqual(len(self.book.prices), 2)
        still = self.book.value_on('2026-01-02')
        kept = [line for line in still.lines if line.kind == 'quantity'][0]
        self.assertEqual(kept.amount, Decimal('8'))
        self.assertEqual(kept.freshness, 'fresh')
        moved = self.book.value_on('2026-01-12')
        used = [line for line in moved.lines if line.kind == 'quantity'][0]
        self.assertEqual(used.amount, Decimal('18'))
        self.assertEqual(used.freshness, 'fresh')

    def test_labels_and_historical_value_do_not_invent_a_price(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '100')
        instrument = self._fund()
        self._buy(account, instrument, '2026-01-03', '2', '40')
        self._price(instrument, '4', 'NOK', '2026-01-02', '2026-01-05')
        self._price(instrument, '7', 'NOK', '2026-01-20', '2026-01-01')
        used = self.book.value_on('2026-01-02')
        quantity = [line for line in used.lines if line.kind == 'quantity']
        self.assertEqual(quantity, [])
        later = self.book.value_on('2026-01-12')
        holding = [line for line in later.lines if line.kind == 'quantity'][0]
        self.assertFalse(holding.known)
        self.assertIsNone(holding.amount)
        self.assertNotEqual(holding.amount, Decimal('8'))
        page = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-01-12',
            None,
        )
        self.assertEqual(page.status, 200)
        price_rows = [
            part.split('</tr>', 1)[0]
            for part in page.body.split('<tr')[1:]
            if 'data-valuation-date=' in part
        ]
        freshness = {
            row.split('data-valuation-date="', 1)[1].split('"', 1)[0]: row
            for row in price_rows
        }
        self.assertIn('data-freshness="stale"', freshness['2026-01-02'])
        self.assertIn(
            'data-freshness="future_valuation"',
            freshness['2026-01-20'],
        )
        self.assertEqual(len(self.book.prices), 2)
        on_its_date = self.book.value_on('2026-01-02')
        self.assertEqual(on_its_date.lines[-1].kind, 'cash')
        evidence = self.book.value_on('2026-01-03')
        self.assertTrue(
            any(line.kind == 'quantity' and not line.known for line in evidence.lines)
        )
        carried = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-01-03',
            None,
        )
        value_row = _value_row(carried.body, 'quantity', instrument)
        self.assertIn('data-known="false"', value_row)
        self.assertNotIn('data-amount', value_row)
        self.assertNotIn('>8<', value_row)
        future = dispatch(
            self.state,
            'POST',
            '/portfolio/valuation?date=2026-01-03',
            {
                'action': 'price',
                'instrument': instrument,
                'amount': '4',
                'currency': 'NOK',
                'valuation_date': '2026-01-03',
                'evidence_date': '2026-01-09',
                'provenance': 'later note',
                'date': '2026-01-03',
            },
        )
        self.assertEqual(future.status, 200)
        valued = self.book.value_on('2026-01-03')
        quantity = [line for line in valued.lines if line.kind == 'quantity'][0]
        self.assertTrue(quantity.known)
        self.assertEqual(quantity.amount, Decimal('8'))
        self.assertEqual(quantity.freshness, 'future_evidence')
        self.assertNotIn('fresh', quantity.freshness)
        row = _value_row(future.body, 'quantity', instrument)
        self.assertIn('data-freshness="future_evidence"', row)
        self.assertIn('data-amount="8"', row)
        history = self.book.value_on('2026-01-05')
        self.assertEqual(
            [point.on_date for point in history.history],
            ['2026-01-01', '2026-01-03', '2026-01-05'],
        )
        by_date = {point.on_date: point for point in history.history}
        self.assertEqual(by_date['2026-01-01'].known_nok_subtotal, Decimal('100'))
        self.assertEqual(by_date['2026-01-01'].unknown_count, 0)
        self.assertEqual(by_date['2026-01-03'].known_nok_subtotal, Decimal('68'))
        self.assertEqual(by_date['2026-01-03'].unknown_count, 0)
        self.assertEqual(by_date['2026-01-05'].known_nok_subtotal, Decimal('60'))
        self.assertEqual(by_date['2026-01-05'].unknown_count, 1)
        self.assertNotEqual(by_date['2026-01-05'].known_nok_subtotal, Decimal('68'))

    def test_same_day_cash_snapshot_is_not_added_to_ledger_cash(self):
        account = self._account()
        self._contribute(account, '2026-01-02', '100')
        ledger_only = self.book.value_on('2026-01-02')
        self.assertEqual(
            [line.kind for line in ledger_only.lines],
            ['cash'],
        )
        self.assertTrue(ledger_only.lines[0].known)
        self.assertEqual(ledger_only.lines[0].amount, Decimal('100'))
        self.assertEqual(ledger_only.known_nok_subtotal, Decimal('100'))
        self.assertTrue(ledger_only.allocation_complete)
        self.assertEqual(ledger_only.note, '')

        saved = self.book.add_manual_balance(
            account,
            'cash',
            '100',
            'NOK',
            '2026-01-02',
            'statement',
        )
        self.assertTrue(saved.accepted)
        report = self.book.value_on('2026-01-02')
        self.assertEqual(
            [line.kind for line in report.lines],
            ['cash', 'snapshot'],
        )
        cash = report.lines[0]
        snapshot = report.lines[1]
        self.assertTrue(cash.known)
        self.assertEqual(cash.amount, Decimal('100'))
        self.assertEqual(cash.currency, 'NOK')
        self.assertTrue(snapshot.known)
        self.assertEqual(snapshot.amount, Decimal('100'))
        self.assertEqual(snapshot.currency, 'NOK')
        self.assertEqual(snapshot.detail, 'snapshot')
        self.assertNotEqual(report.known_nok_subtotal, Decimal('200'))
        self.assertEqual(report.known_nok_subtotal, Decimal('100'))
        self.assertFalse(report.allocation_complete)
        self.assertEqual(report.shares, ())
        self.assertEqual(report.note, CASH_SNAPSHOT_NOT_ADDED)
        self.assertEqual(report.error, '')
        page = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-01-02',
            None,
        )
        self.assertEqual(page.status, 200)
        self.assertEqual(page.body.count(CASH_SNAPSHOT_NOT_ADDED), 1)
        self.assertIn('Allocation is incomplete.', page.body)
        self.assertIn('data-amount="100"', _value_row(page.body, 'cash', 'NOK'))
        self.assertIn(
            'data-amount="100"',
            _value_row(page.body, 'snapshot', 'cash'),
        )
        self.assertNotIn('data-nok-subtotal="200"', page.body)
        self.assertNotIn('data-share', page.body)

        solo = EnteredPortfolio(Path(self._tmp.name) / 'solo.json')
        solo_account = solo.add_account('Bank', 'Solo').identity
        withdrawn = solo.add_activity(
            'contribution',
            solo_account,
            '2026-03-01',
            'transfer',
            currency='NOK',
            amount='100',
        )
        self.assertTrue(withdrawn.accepted)
        cleared = solo.add_activity(
            'withdrawal',
            solo_account,
            '2026-03-02',
            'transfer',
            currency='NOK',
            amount='100',
        )
        self.assertTrue(cleared.accepted)
        self.assertEqual(solo.books().cash, ())
        only_snapshot = solo.add_manual_balance(
            solo_account,
            'cash',
            '100',
            'NOK',
            '2026-03-02',
            'statement',
        )
        self.assertTrue(only_snapshot.accepted)
        zero_cash = solo.value_on('2026-03-02')
        self.assertEqual(
            [line.kind for line in zero_cash.lines],
            ['snapshot'],
        )
        self.assertTrue(zero_cash.lines[0].known)
        self.assertEqual(zero_cash.lines[0].amount, Decimal('100'))
        self.assertEqual(zero_cash.known_nok_subtotal, Decimal('100'))
        self.assertTrue(zero_cash.allocation_complete)
        self.assertEqual(zero_cash.note, '')

    def test_manual_balance_is_a_snapshot_and_not_a_price(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '100')
        instrument = self._fund('USD')
        saved = self.book.add_manual_balance(
            account,
            instrument,
            '10',
            'USD',
            '2026-01-02',
            'statement',
        )
        self.assertTrue(saved.accepted)
        self._price(instrument, '99', 'USD', '2026-01-02')
        on_date = self.book.value_on('2026-01-02')
        self.assertEqual(
            [line.kind for line in on_date.lines],
            ['cash', 'snapshot'],
        )
        snapshot = on_date.lines[1]
        self.assertTrue(snapshot.known)
        self.assertEqual(snapshot.amount, Decimal('10'))
        self.assertEqual(snapshot.currency, 'USD')
        self.assertEqual(snapshot.detail, 'snapshot')
        self.assertNotEqual(snapshot.amount, Decimal('99'))
        self.assertEqual(on_date.known_nok_subtotal, Decimal('100'))
        self.assertEqual(self.book.books().positions, ())
        other = self.book.value_on('2026-01-04')
        missed = [line for line in other.lines if line.kind == 'snapshot'][0]
        self.assertFalse(missed.known)
        self.assertIsNone(missed.amount)
        self.assertEqual(missed.detail, NO_SNAPSHOT)
        self.assertNotEqual(missed.amount, Decimal(0))
        self.assertNotEqual(missed.amount, Decimal('10'))
        page = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-01-04',
            None,
        )
        row = _value_row(page.body, 'snapshot', instrument)
        self.assertIn(NO_SNAPSHOT, row)
        self.assertIn('unknown', row)
        self.assertNotIn('data-amount', row)
        self.assertNotIn('>10<', row)
        self.assertNotIn('>99<', row)

    def test_allocation_shares_only_when_every_line_is_known_nok(self):
        account = self._account()
        self._contribute(account, '2026-01-01', '200')
        instrument = self._fund()
        self._buy(account, instrument, '2026-01-02', '2', '100')
        self._price(instrument, '50', 'NOK', '2026-01-02')
        report = self.book.value_on('2026-01-02')
        self.assertTrue(report.allocation_complete)
        self.assertEqual(report.known_nok_subtotal, Decimal('200'))
        self.assertEqual(report.shares, (Decimal('0.5'), Decimal('0.5')))
        self.assertEqual(sum(report.shares, Decimal(0)), Decimal(1))
        page = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-01-02',
            None,
        )
        self.assertNotIn('Allocation is incomplete.', page.body)
        self.assertIn('data-share="0.5"', page.body)
        self.assertIn('known NOK subtotal', page.body)
        usd = self._account_usd_line()
        mixed = usd.value_on('2026-02-01')
        self.assertFalse(mixed.allocation_complete)
        self.assertEqual(mixed.known_nok_subtotal, Decimal('100'))
        self.assertEqual(mixed.shares, ())
        carried = [line for line in mixed.lines if line.kind == 'quantity'][0]
        self.assertIsNone(carried.amount)
        dollar = [
            line for line in mixed.lines
            if line.kind == 'cash' and line.currency == 'USD'
        ][0]
        self.assertEqual(dollar.amount, Decimal('40'))
        foreign = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-02-01',
            None,
        )
        self.assertIn('Allocation is incomplete.', foreign.body)
        self.assertNotIn('data-share', foreign.body)
        self.assertIn('known NOK subtotal', foreign.body)
        self.assertIn('>40<', _value_row(foreign.body, 'cash', 'USD'))
        self.assertNotIn('10.25', foreign.body)
        self.assertNotIn('410', foreign.body)

    def test_known_nok_subtotal_of_zero_says_allocation_is_incomplete(self):
        account = self._account()
        self._contribute(account, '2026-04-01', '100')
        instrument = self._fund()
        self._buy(account, instrument, '2026-04-02', '1', '100')
        self._price(instrument, '0', 'NOK', '2026-04-02')
        report = self.book.value_on('2026-04-02')
        self.assertEqual(report.error, '')
        self.assertTrue(report.lines)
        self.assertTrue(all(
            line.known and line.currency == 'NOK' for line in report.lines
        ))
        self.assertEqual(report.known_nok_subtotal, Decimal(0))
        self.assertEqual(report.shares, ())
        self.assertEqual(report.note, '')
        page = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-04-02',
            None,
        )
        self.assertEqual(page.status, 200)
        self.assertEqual(page.body.count('Allocation is incomplete.'), 1)
        self.assertNotIn('data-share', page.body)
        self.assertNotIn('<h2>Allocation</h2>', page.body)
        self.assertIn(
            'data-nok-subtotal="0">known NOK subtotal '
            '<span class="figure">0</span>',
            page.body,
        )
        self.assertEqual(self.book.ledger()._prices, [])
        self.assertEqual(self.book.ledger()._rates, [])
        empty = dispatch(self.state, 'GET', '/portfolio/valuation', None)
        self.assertEqual(empty.status, 200)
        self.assertIn('Enter the date.', empty.body)
        self.assertEqual(empty.body.count('Allocation is incomplete.'), 1)
        self.assertNotIn('data-share', empty.body)
        self.assertNotIn('<h2>Allocation</h2>', empty.body)

    def _account_usd_line(self):
        account = self.book.add_account('Bank', 'Dollar').identity
        self._contribute(account, '2026-02-01', '40', 'USD')
        return self.book

    def test_decimal_product_ignores_a_lowered_context(self):
        account = self._account()
        self._contribute(account, '2026-03-01', '10')
        instrument = self._fund()
        self._buy(account, instrument, '2026-03-02', '1.25', '1')
        self._price(instrument, '1.25', 'NOK', '2026-03-02')
        with localcontext(Context(prec=2)):
            report = self.book.value_on('2026-03-02')
        quantity = [line for line in report.lines if line.kind == 'quantity'][0]
        self.assertEqual(quantity.amount, Decimal('1.5625'))
        self.assertIsInstance(quantity.amount, Decimal)

    def test_page_is_reached_from_the_entered_portfolio_without_a_new_process(self):
        import socket
        import urllib.request

        account = self._account()
        self._contribute(account, '2026-01-01', '15')
        portfolio = dispatch(self.state, 'GET', '/portfolio', None)
        self.assertIn('href="/portfolio/valuation?date=2026-01-01"', portfolio.body)
        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen
        socket_type = socket.socket

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        socket.socket = blocked
        try:
            page = dispatch(
                self.state,
                'GET',
                '/portfolio/valuation?date=2026-01-01',
                None,
            )
        finally:
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
            socket.socket = socket_type
        self.assertEqual(page.status, 200)
        self.assertEqual(page.body.count(VALUATION_SENTENCE), 1)
        self.assertEqual(page.body.count(MISSING_PRICE_SENTENCE), 1)
        self.assertEqual(page.body.count(SNAPSHOT_VALUE_SENTENCE), 1)
        self.assertIn('known NOK subtotal', page.body)
        self.assertIn('data-history="2026-01-01"', page.body)
        self.assertNotIn('These figures are synthetic', page.body)
        self.assertNotIn('10.25', page.body)
        ledger = dispatch(self.state, 'GET', '/ledger', None)
        self.assertIn('15050', ledger.body)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )
        self.assertEqual(list(self.state.price_postings), self._price_postings)
        self.assertEqual(list(self.state.rate_postings), self._rate_postings)
        source = (
            ROOT / 'src' / 'huginn_muninn' / 'onboarding.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn('add_price', source)
        self.assertNotIn('add_rate', source)
        self.assertNotIn('evidence_observations', source)
        empty = dispatch(self.state, 'GET', '/portfolio/valuation', None)
        self.assertEqual(empty.status, 200)
        self.assertIn('Enter the date.', empty.body)
        self.assertEqual(empty.body.count(VALUATION_SENTENCE), 1)


ATTRIBUTION_UNAVAILABLE = 'Attribution is unavailable.'
ATTRIBUTION_SENTENCE = 'This attribution is not a recommendation.'
FEE_SENTENCE = 'A fee is cash leaving, not a market gain.'
DIVIDEND_SENTENCE = (
    'A dividend is cash received. It is not a contribution and it is not '
    'a price change.'
)
START_AFTER_END = 'The start date is after the end date.'


class EnteredPerformanceTest(unittest.TestCase):
    def setUp(self):
        self._before_fixture = FIXTURE.read_bytes()
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.overlay = root / 'synthetic-book.json'
        self.entered_path = root / 'book.json'
        self.state = open_state(ROOT, self.overlay, self.entered_path)
        self.book = self.state.entered
        self._price_postings = list(self.state.price_postings)
        self._rate_postings = list(self.state.rate_postings)

    def tearDown(self):
        self.assertEqual(FIXTURE.read_bytes(), self._before_fixture)
        self._tmp.cleanup()

    def _account(self):
        saved = self.book.add_account('Bank', 'Main')
        self.assertTrue(saved.accepted)
        return saved.identity

    def _fund(self):
        saved = self.book.add_instrument('Local fund', 'fund', 'NOK')
        self.assertTrue(saved.accepted)
        return saved.identity

    def _activity(self, activity, account, day, **values):
        saved = self.book.add_activity(
            activity,
            account,
            day,
            'statement',
            **values,
        )
        self.assertTrue(saved.accepted, saved.message)
        return saved

    def _contribute(self, account, day, amount, currency='NOK'):
        self._activity(
            'contribution',
            account,
            day,
            currency=currency,
            amount=amount,
        )

    def _buy(self, account, instrument, day, quantity, cash, fee):
        self._activity(
            'purchase',
            account,
            day,
            instrument=instrument,
            quantity=quantity,
            cash_currency='NOK',
            cash_amount=cash,
            fee=fee,
        )

    def _sell(self, account, instrument, day, quantity, cash, fee):
        self._activity(
            'sale',
            account,
            day,
            instrument=instrument,
            quantity=quantity,
            cash_currency='NOK',
            cash_amount=cash,
            fee=fee,
        )

    def _price(self, instrument, amount, day):
        saved = self.book.record_price(
            instrument,
            amount,
            'NOK',
            day,
            day,
            'statement',
        )
        self.assertTrue(saved.accepted, saved.message)

    def _page(self, start, end):
        return dispatch(
            self.state,
            'GET',
            f'/portfolio/performance?start={start}&end={end}',
            None,
        )

    def _assert_decimal(self, amount, expected):
        self.assertIsInstance(amount, Decimal)
        self.assertNotIsInstance(amount, float)
        self.assertEqual(amount, Decimal(expected))

    def _assert_figures(self, report, **expected):
        for name, value in expected.items():
            self._assert_decimal(getattr(report, name), value)

    def _locked_book(self):
        account = self._account()
        self._contribute(account, '2026-05-01', '1000')
        instrument = self._fund()
        self._buy(account, instrument, '2026-05-02', '10', '500', '10')
        self._price(instrument, '50', '2026-05-02')
        self._price(instrument, '60', '2026-05-03')
        self.assertEqual(self.book.books().cash[0].amount, Decimal('490'))
        self.assertEqual(self.book.books().positions[0].quantity, Decimal('10'))
        return account, instrument

    def test_locked_window_separates_the_fee_from_the_price_change(self):
        self._locked_book()
        with localcontext(Context(prec=2)):
            first = self.book.attribute('2026-05-01', '2026-05-02')
            second = self.book.attribute('2026-05-01', '2026-05-03')
        self.assertEqual(first.error, '')
        self.assertFalse(first.unavailable)
        self._assert_figures(
            first,
            start_value='1000',
            end_value='990',
            contributions='0',
            withdrawals='0',
            fees='10',
            dividends='0',
            price_change='0',
        )
        self._assert_figures(
            second,
            start_value='1000',
            end_value='1090',
            contributions='0',
            withdrawals='0',
            fees='10',
            dividends='0',
            price_change='100',
        )
        early = self._page('2026-05-01', '2026-05-02')
        self.assertEqual(early.status, 200)
        self.assertEqual(early.body.count(ATTRIBUTION_SENTENCE), 1)
        self.assertEqual(early.body.count(FEE_SENTENCE), 1)
        self.assertEqual(early.body.count(DIVIDEND_SENTENCE), 1)
        self.assertNotIn(ATTRIBUTION_UNAVAILABLE, early.body)
        self.assertIn('data-start-value="1000"', early.body)
        self.assertIn('>start value <span class="figure">1000</span>', early.body)
        self.assertIn('data-end-value="990"', early.body)
        self.assertIn('>end value <span class="figure">990</span>', early.body)
        self.assertIn('data-contributions="0"', early.body)
        self.assertIn('>contributions <span class="figure">0</span>', early.body)
        self.assertIn('data-withdrawals="0"', early.body)
        self.assertIn('>withdrawals <span class="figure">0</span>', early.body)
        self.assertIn('data-fees="10"', early.body)
        self.assertIn('>fees <span class="figure">10</span>', early.body)
        self.assertIn('data-dividends="0"', early.body)
        self.assertIn('>dividends <span class="figure">0</span>', early.body)
        self.assertEqual(early.body.count('data-price-change="0"'), 1)
        self.assertIn('>price change <span class="figure">0</span>', early.body)
        self.assertIn('name="start"', early.body)
        self.assertIn('name="end"', early.body)
        later = self._page('2026-05-01', '2026-05-03')
        self.assertIn('data-end-value="1090"', later.body)
        self.assertIn('data-fees="10"', later.body)
        self.assertEqual(later.body.count('data-price-change="100"'), 1)
        self.assertIn('>price change <span class="figure">100</span>', later.body)
        valuation = dispatch(
            self.state,
            'GET',
            '/portfolio/valuation?date=2026-05-02',
            None,
        )
        self.assertIn('href="/portfolio/performance"', valuation.body)
        reversed_dates = self._page('2026-05-03', '2026-05-01')
        self.assertIn(START_AFTER_END, reversed_dates.body)
        self.assertNotIn('price change', reversed_dates.body)
        self.assertNotIn('data-price-change', reversed_dates.body)
        self.assertNotIn(ATTRIBUTION_UNAVAILABLE, reversed_dates.body)
        ledger = dispatch(self.state, 'GET', '/ledger', None)
        self.assertIn('15050', ledger.body)
        self.assertEqual(
            [row['rate'] for row, _posting in self.state.rate_postings],
            ['10', '10.25'],
        )
        self.assertEqual(list(self.state.price_postings), self._price_postings)
        self.assertEqual(list(self.state.rate_postings), self._rate_postings)
        self.assertNotIn('10.25', early.body)
        self.assertNotIn('15050', early.body)
        source = (
            ROOT / 'src' / 'huginn_muninn' / 'onboarding.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn('add_price', source)
        self.assertNotIn('add_rate', source)

    def test_any_manual_balance_makes_attribution_unavailable(self):
        account = self._account()
        saved = self.book.add_manual_balance(
            account,
            'cash',
            '100',
            'NOK',
            '2026-05-01',
            'statement',
        )
        self.assertTrue(saved.accepted, saved.message)
        valued = self.book.value_on('2026-05-01')
        snapshot = [line for line in valued.lines if line.kind == 'snapshot'][0]
        self.assertTrue(snapshot.known)
        self.assertEqual(snapshot.amount, Decimal('100'))
        report = self.book.attribute('2026-05-01', '2026-05-01')
        self.assertTrue(report.unavailable)
        self.assertIsNone(report.price_change)
        self.assertEqual(report.error, '')
        page = self._page('2026-05-01', '2026-05-01')
        self.assertEqual(page.status, 200)
        self.assertEqual(page.body.count(ATTRIBUTION_UNAVAILABLE), 1)
        self.assertNotIn('price change', page.body)
        self.assertNotIn('data-price-change', page.body)
        self.assertNotIn('data-start-value', page.body)

    def test_a_missing_price_makes_attribution_unavailable(self):
        account = self._account()
        self._contribute(account, '2026-05-01', '1000')
        instrument = self._fund()
        self._buy(account, instrument, '2026-05-02', '10', '500', '0')
        report = self.book.attribute('2026-05-01', '2026-05-02')
        self.assertTrue(report.unavailable)
        self.assertIsNone(report.price_change)
        page = self._page('2026-05-01', '2026-05-02')
        self.assertEqual(page.body.count(ATTRIBUTION_UNAVAILABLE), 1)
        self.assertNotIn('price change', page.body)
        self.assertNotIn('data-price-change', page.body)
        self.assertNotIn('data-end-value', page.body)

    def test_usd_cash_makes_attribution_unavailable(self):
        account = self._account()
        self._contribute(account, '2026-02-01', '40', 'USD')
        report = self.book.attribute('2026-02-01', '2026-02-01')
        self.assertTrue(report.unavailable)
        self.assertIsNone(report.price_change)
        page = self._page('2026-02-01', '2026-02-01')
        self.assertEqual(page.body.count(ATTRIBUTION_UNAVAILABLE), 1)
        self.assertNotIn('price change', page.body)
        self.assertNotIn('data-price-change', page.body)
        self.assertNotIn('10.25', page.body)
        self.assertNotIn('410', page.body)

    def test_a_flow_that_is_not_nok_makes_attribution_unavailable(self):
        account = self._account()
        self._contribute(account, '2026-06-01', '1000')
        self._contribute(account, '2026-06-02', '10', 'USD')
        self._activity(
            'fee',
            account,
            '2026-06-02',
            currency='USD',
            amount='10',
        )
        start = self.book.value_on('2026-06-01')
        end = self.book.value_on('2026-06-02')
        self.assertTrue(all(
            line.known and line.currency == 'NOK' for line in start.lines
        ))
        self.assertTrue(all(
            line.known and line.currency == 'NOK' for line in end.lines
        ))
        self.assertEqual(start.known_nok_subtotal, Decimal('1000'))
        self.assertEqual(end.known_nok_subtotal, Decimal('1000'))
        report = self.book.attribute('2026-06-01', '2026-06-02')
        self.assertTrue(report.unavailable)
        self.assertIsNone(report.price_change)
        page = self._page('2026-06-01', '2026-06-02')
        self.assertEqual(page.body.count(ATTRIBUTION_UNAVAILABLE), 1)
        self.assertNotIn('price change', page.body)
        self.assertNotIn('data-price-change', page.body)

    def test_a_nok_dividend_is_not_inside_the_price_change(self):
        account = self._account()
        self._contribute(account, '2026-05-01', '1000')
        instrument = self._fund()
        self._buy(account, instrument, '2026-05-02', '10', '500', '0')
        self._price(instrument, '50', '2026-05-02')
        self._price(instrument, '50', '2026-05-03')
        self._activity(
            'dividend',
            account,
            '2026-05-03',
            instrument=instrument,
            currency='NOK',
            amount='40',
        )
        report = self.book.attribute('2026-05-01', '2026-05-03')
        self.assertFalse(report.unavailable)
        self._assert_figures(
            report,
            start_value='1000',
            end_value='1040',
            contributions='0',
            withdrawals='0',
            fees='0',
            dividends='40',
            price_change='0',
        )
        self.assertNotEqual(report.price_change, report.dividends)
        page = self._page('2026-05-01', '2026-05-03')
        self.assertIn(DIVIDEND_SENTENCE, page.body)
        self.assertIn('data-dividends="40"', page.body)
        self.assertIn('>dividends <span class="figure">40</span>', page.body)
        self.assertEqual(page.body.count('data-price-change="0"'), 1)
        self.assertIn('data-contributions="0"', page.body)

    def test_a_later_contribution_withdrawal_fee_and_sale_fee(self):
        account = self._account()
        self._contribute(account, '2026-07-01', '1000')
        instrument = self._fund()
        self._buy(account, instrument, '2026-07-02', '10', '500', '0')
        self._price(instrument, '50', '2026-07-02')
        self._contribute(account, '2026-07-03', '125')
        self._activity(
            'withdrawal',
            account,
            '2026-07-03',
            currency='NOK',
            amount='40',
        )
        self._activity(
            'fee',
            account,
            '2026-07-03',
            currency='NOK',
            amount='25',
        )
        self._price(instrument, '50', '2026-07-03')
        self._sell(account, instrument, '2026-07-04', '10', '500', '12')
        held = self.book.attribute('2026-07-01', '2026-07-03')
        # Cash 1000 - 500 + 125 - 40 - 25 = 560. Position 10 * 50 = 500.
        self._assert_figures(
            held,
            start_value='1000',
            end_value='1060',
            contributions='125',
            withdrawals='40',
            fees='25',
            dividends='0',
            price_change='0',
        )
        closed = self.book.attribute('2026-07-01', '2026-07-04')
        # Sale returns 500 and pays fee 12. Position is gone. Cash 1048.
        self._assert_figures(
            closed,
            start_value='1000',
            end_value='1048',
            contributions='125',
            withdrawals='40',
            fees='37',
            dividends='0',
            price_change='0',
        )
        page = self._page('2026-07-01', '2026-07-04')
        self.assertIn('data-contributions="125"', page.body)
        self.assertIn('data-withdrawals="40"', page.body)
        self.assertIn('data-fees="37"', page.body)
        self.assertEqual(page.body.count('data-price-change="0"'), 1)

    def test_get_performance_does_not_fetch(self):
        import socket
        import urllib.request

        self._locked_book()
        opener = urllib.request.build_opener
        urlopen = urllib.request.urlopen
        socket_type = socket.socket

        def blocked(*args, **kwargs):
            raise AssertionError('network')

        urllib.request.build_opener = blocked
        urllib.request.urlopen = blocked
        socket.socket = blocked
        try:
            empty = dispatch(self.state, 'GET', '/portfolio/performance', None)
            page = self._page('2026-05-01', '2026-05-03')
        finally:
            urllib.request.build_opener = opener
            urllib.request.urlopen = urlopen
            socket.socket = socket_type
        self.assertEqual(empty.status, 200)
        self.assertIn('Enter the start date.', empty.body)
        self.assertIn('Enter the end date.', empty.body)
        self.assertIn('name="start"', empty.body)
        self.assertIn('name="end"', empty.body)
        self.assertNotIn('price change', empty.body)
        self.assertNotIn(ATTRIBUTION_UNAVAILABLE, empty.body)
        self.assertEqual(empty.body.count(ATTRIBUTION_SENTENCE), 1)
        self.assertEqual(page.status, 200)
        self.assertIn('data-price-change="100"', page.body)
        self.assertIn('text/html', page.content_type)
        ledger = dispatch(self.state, 'GET', '/ledger', None)
        self.assertIn('15050', ledger.body)
