import json
import tempfile
import unittest
from decimal import ROUND_HALF_EVEN, Context, Decimal, getcontext, localcontext
from pathlib import Path

from src.huginn_muninn.allocation import ARITHMETIC_SENTENCE, compare
from src.huginn_muninn.desk import INTELLIGENCE
from src.huginn_muninn.ledger import (
    Account,
    Buy,
    Deposit,
    Dividend,
    Instrument,
    Ledger,
    PriceObservation,
    Sell,
)
from src.huginn_muninn.prototype import dispatch, open_state


ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'fixtures' / 'synthetic_portfolio.json'
_LOCKED_LITERALS = (
    '24932.50',
    '1432.50',
    '15050',
    '4752.875',
    '5310.625',
)


def _document():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def _targets():
    return {
        key: Decimal(value)
        for key, value in _document()['targets'].items()
    }


def _listings():
    return {
        row['identity']: row['listing_currency']
        for row in _document()['instruments']
    }


def _position(performance, identity):
    matches = [
        row for row in performance.positions if row.instrument == identity
    ]
    if len(matches) != 1:
        raise AssertionError(performance.positions)
    return matches[0]


def _last_reply(body):
    marker = '<p class="reply">'
    start = body.rfind(marker)
    if start < 0:
        raise AssertionError('missing reply')
    end = body.find('</p>', start)
    return body[start + len(marker):end]


class DeskTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.overlay = Path(self._tmp.name) / 'synthetic-book.json'
        self.state = open_state(ROOT, self.overlay)

    def tearDown(self):
        self._tmp.cleanup()

    def test_locked_performance_identity(self):
        ledger = self.state.ledger
        before_books = ledger.books('2026-03-31')
        before_value = ledger.value('2026-03-31')
        result = ledger.performance('2026-03-31')
        self.assertEqual(ledger.books('2026-03-31'), before_books)
        self.assertEqual(ledger.value('2026-03-31'), before_value)
        self.assertTrue(before_value.complete)
        self.assertEqual(before_value.known_subtotal, Decimal('24932.50'))
        north = _position(result, 'northline')
        harbor = _position(result, 'harbor')
        self.assertEqual(north.quantity, Decimal('16'))
        self.assertEqual(north.cost, Decimal('8012'))
        self.assertEqual(north.cost_currency, 'NOK')
        self.assertEqual(harbor.quantity, Decimal('5'))
        self.assertEqual(harbor.cost, Decimal('805'))
        self.assertEqual(harbor.cost_currency, 'NOK')
        self.assertEqual(len(result.realized), 1)
        self.assertEqual(result.realized[0].gain, Decimal('287'))
        self.assertEqual(result.realized[0].reasons, ())
        unrealized = {row.instrument: row for row in result.unrealized}
        self.assertEqual(unrealized['northline'].gain, Decimal('948'))
        self.assertEqual(unrealized['harbor'].gain, Decimal('117.50'))
        self.assertIsNone(unrealized['harbor'].rate_id)
        self.assertEqual(result.dividend_income, Decimal('80'))
        self.assertEqual(result.residual, Decimal('1432.50'))
        self.assertEqual(result.residual_reasons, ())
        self.assertEqual(
            result.residual,
            result.realized[0].gain
            + result.dividend_income
            + unrealized['northline'].gain
            + unrealized['harbor'].gain,
        )

    def test_incomplete_date_leaves_residual_and_harbor_unrealized_unknown(self):
        ledger = self.state.ledger
        valuation = ledger.value('2026-03-10')
        result = ledger.performance('2026-03-10')
        self.assertFalse(valuation.complete)
        self.assertIsNone(result.residual)
        self.assertIn('incomplete', result.residual_reasons)
        harbor = {row.instrument: row for row in result.unrealized}['harbor']
        self.assertIsNone(harbor.gain)
        self.assertIsNone(harbor.reporting_amount)
        self.assertIn('missing_rate', harbor.reasons)
        self.assertNotEqual(harbor.gain, Decimal('0'))
        north = _position(result, 'northline')
        self.assertEqual(north.quantity, Decimal('16'))
        self.assertEqual(north.cost, Decimal('8012'))

    def test_second_buy_in_another_cash_currency_does_not_invent_a_gain(self):
        ledger = Ledger('NOK')
        ledger.add_account(Account('brokerage'))
        ledger.add_instrument(Instrument('northline', 'NOK'))
        self.assertTrue(ledger.record(Deposit(
            'dep-nok', 'brokerage', 'NOK', Decimal('5000'),
            '2026-04-01', 'synthetic-nok',
        )).accepted)
        self.assertTrue(ledger.record(Deposit(
            'dep-usd', 'brokerage', 'USD', Decimal('100'),
            '2026-04-02', 'synthetic-usd',
        )).accepted)
        self.assertTrue(ledger.record(Buy(
            'buy-nok', 'brokerage', 'northline', Decimal('10'), 'NOK',
            Decimal('1000'), Decimal('0'), '2026-04-03', 'synthetic-buy-nok',
        )).accepted)
        rejected = ledger.record(Buy(
            'buy-too-much', 'brokerage', 'northline', Decimal('1'), 'USD',
            Decimal('500'), Decimal('0'), '2026-04-04', 'synthetic-rejected',
        ))
        self.assertFalse(rejected.accepted)
        still_known = ledger.performance('2026-04-04')
        self.assertEqual(still_known.positions[0].cost, Decimal('1000'))
        self.assertEqual(still_known.positions[0].cost_currency, 'NOK')
        self.assertTrue(ledger.record(Buy(
            'buy-usd', 'brokerage', 'northline', Decimal('4'), 'USD',
            Decimal('40'), Decimal('1'), '2026-04-05', 'synthetic-buy-usd',
        )).accepted)
        mixed = ledger.performance('2026-04-05')
        self.assertEqual(mixed.positions[0].quantity, Decimal('14'))
        self.assertIsNone(mixed.positions[0].cost)
        self.assertIn('mixed_cost_currency', mixed.positions[0].reasons)
        self.assertTrue(ledger.record(Sell(
            'sell-mixed', 'brokerage', 'northline', Decimal('2'), 'NOK',
            Decimal('300'), Decimal('0'), '2026-04-06', 'synthetic-sell',
        )).accepted)
        self.assertTrue(ledger.add_price(PriceObservation(
            'px', 'northline', Decimal('10'), 'NOK',
            '2026-04-06', '2026-04-06', 'synthetic-price',
        )).accepted)
        after = ledger.performance('2026-04-06')
        self.assertEqual(after.positions[0].quantity, Decimal('12'))
        self.assertIsNone(after.positions[0].cost)
        self.assertIsNone(after.realized[-1].gain)
        self.assertIn('mixed_cost_currency', after.realized[-1].reasons)
        self.assertIsNotNone(after.unrealized[0].reporting_amount)
        self.assertIsNone(after.unrealized[0].gain)
        self.assertEqual(
            ledger.books('2026-04-06').positions[0].quantity,
            Decimal('12'),
        )

    def test_foreign_dividend_is_excluded_from_reporting_income(self):
        ledger = Ledger('NOK')
        ledger.add_account(Account('brokerage'))
        ledger.add_instrument(Instrument('northline', 'NOK'))
        ledger.record(Deposit(
            'dep', 'brokerage', 'NOK', Decimal('100'),
            '2026-05-01', 'synthetic',
        ))
        ledger.record(Buy(
            'buy', 'brokerage', 'northline', Decimal('1'), 'NOK',
            Decimal('10'), Decimal('0'), '2026-05-02', 'synthetic',
        ))
        posting = ledger.record(Dividend(
            'div', 'brokerage', 'northline', 'USD', Decimal('12'),
            '2026-05-03', 'synthetic',
        ))
        self.assertTrue(posting.accepted)
        result = ledger.performance('2026-05-03')
        self.assertEqual(result.dividend_income, Decimal('0'))
        self.assertEqual(len(result.dividends), 1)
        self.assertFalse(result.dividends[0].included)
        self.assertEqual(result.dividends[0].amount, Decimal('12'))
        self.assertEqual(result.dividends[0].reasons, ('currency_mismatch',))

    def test_cost_fraction_ignores_lowered_caller_precision(self):
        ledger = Ledger('NOK')
        ledger.add_account(Account('brokerage'))
        ledger.add_instrument(Instrument('line', 'NOK'))
        ledger.record(Deposit(
            'dep', 'brokerage', 'NOK', Decimal('10'),
            '2026-05-01', 'synthetic',
        ))
        ledger.record(Buy(
            'buy', 'brokerage', 'line', Decimal('3'), 'NOK',
            Decimal('1.0000001'), Decimal('0'), '2026-05-02', 'synthetic',
        ))
        ledger.record(Sell(
            'sell', 'brokerage', 'line', Decimal('1'), 'NOK',
            Decimal('1'), Decimal('0'), '2026-05-03', 'synthetic',
        ))
        original = getcontext().prec
        getcontext().prec = 6
        try:
            result = ledger.performance('2026-05-03')
            self.assertEqual(getcontext().prec, 6)
            with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
                expected = Decimal('1.0000001') * Decimal('1') / Decimal('3')
            with localcontext(Context(prec=6, rounding=ROUND_HALF_EVEN)):
                rounded = Decimal('1.0000001') * Decimal('1') / Decimal('3')
            self.assertEqual(result.realized[0].removed_cost, expected)
            self.assertNotEqual(result.realized[0].removed_cost, rounded)
        finally:
            getcontext().prec = original

    def test_locked_illustrative_amounts_come_from_the_fixture(self):
        source = (ROOT / 'src' / 'huginn_muninn' / 'allocation.py').read_text(
            encoding='utf-8',
        )
        for literal in ('0.20', '0.55', '0.25', '4752.875', '5310.625', '-10063.50'):
            self.assertNotIn(literal, source)
        document = _document()
        self.assertEqual(
            document['targets'],
            {'cash:NOK': '0.20', 'northline': '0.55', 'harbor': '0.25'},
        )
        valuation = self.state.ledger.value('2026-03-31')
        result = compare(valuation, _targets(), _listings())
        self.assertTrue(valuation.complete)
        self.assertEqual(result.status, 'complete')
        self.assertEqual(result.sentence, ARITHMETIC_SENTENCE)
        rows = {row.key: row for row in result.rows}
        self.assertEqual(rows['cash:NOK'].kind, 'arithmetic_gap')
        self.assertEqual(rows['cash:NOK'].illustrative_amount, Decimal('-10063.50'))
        self.assertEqual(rows['northline'].illustrative_amount, Decimal('4752.875'))
        self.assertEqual(rows['harbor'].illustrative_amount, Decimal('5310.625'))
        for row in result.rows:
            self.assertIsNone(row.recommendation)
        self.assertEqual(result.exposure_label, 'listing-currency exposure')
        exposure = {
            row.listing_currency: row.reporting_amount
            for row in result.exposure
        }
        self.assertEqual(exposure['NOK'], Decimal('24010'))
        self.assertEqual(exposure['USD'], Decimal('922.50'))

    def test_incomplete_valuation_has_no_illustrative_amounts(self):
        valuation = self.state.ledger.value('2026-03-10')
        result = compare(valuation, _targets(), _listings())
        self.assertFalse(valuation.complete)
        self.assertEqual(result.status, 'incomplete')
        self.assertEqual(result.rows, ())
        self.assertTrue(any(
            'missing_rate' in item.reasons for item in result.valuation_reasons
        ))
        response = dispatch(self.state, 'GET', '/?date=2026-03-10', None)
        self.assertEqual(response.status, 200)
        self.assertIn('Illustrative amounts are absent', response.body)
        self.assertIn('missing_rate', response.body)
        self.assertNotIn('4752.875', response.body)
        self.assertNotIn('5310.625', response.body)
        self.assertIn('The residual is unknown because the valuation is incomplete.', response.body)

    def test_invalid_targets_have_no_gap_amounts(self):
        valuation = self.state.ledger.value('2026-03-31')
        result = compare(
            valuation,
            {'cash:NOK': Decimal('0.50'), 'northline': Decimal('0.60')},
            _listings(),
        )
        self.assertEqual(result.status, 'invalid_targets')
        self.assertEqual(result.rows, ())
        refused = compare(valuation, {'cash:NOK': '1'}, _listings())
        self.assertEqual(refused.status, 'invalid_targets')
        self.assertEqual(refused.rows, ())

    def test_untargeted_holding_has_no_illustrative_amount(self):
        valuation = self.state.ledger.value('2026-03-31')
        result = compare(
            valuation,
            {'cash:NOK': Decimal('0.40'), 'northline': Decimal('0.60')},
            _listings(),
        )
        self.assertEqual(result.status, 'complete')
        harbor = [row for row in result.rows if row.key == 'harbor']
        self.assertEqual(len(harbor), 1)
        self.assertEqual(harbor[0].kind, 'untargeted')
        self.assertIsNone(harbor[0].illustrative_amount)
        self.assertIsNone(harbor[0].recommendation)
        self.assertEqual(harbor[0].current_amount, Decimal('922.50'))

    def test_api_desk_matches_value_and_rejects_a_bad_date(self):
        response = dispatch(self.state, 'GET', '/api/desk?date=2026-03-31', None)
        self.assertEqual(response.status, 200)
        self.assertIn('json', response.content_type)
        payload = json.loads(response.body)
        valuation = self.state.ledger.value('2026-03-31')
        self.assertEqual(
            payload['known_subtotal'],
            format(valuation.known_subtotal, 'f'),
        )
        self.assertEqual(Decimal(payload['known_subtotal']), valuation.known_subtotal)
        self.assertIs(payload['complete'], True)
        early = dispatch(self.state, 'GET', '/api/desk?date=2026-03-10', None)
        self.assertEqual(early.status, 200)
        early_payload = json.loads(early.body)
        early_value = self.state.ledger.value('2026-03-10')
        self.assertEqual(
            Decimal(early_payload['known_subtotal']),
            early_value.known_subtotal,
        )
        self.assertIs(early_payload['complete'], False)
        harbor = next(
            row for row in early_payload['holdings'] if row['identity'] == 'harbor'
        )
        self.assertIsNone(harbor['reporting_amount'])
        self.assertIn('"reporting_amount": null', early.body)
        self.assertNotIn('"reporting_amount": "0"', early.body)
        self.assertNotIn('"reporting_amount": 0', early.body)
        bad = dispatch(self.state, 'GET', '/api/desk?date=2026-02-31', None)
        self.assertEqual(bad.status, 400)
        missing = dispatch(self.state, 'GET', '/api/desk', None)
        self.assertEqual(missing.status, 400)

    def test_desk_home_is_rendered_from_the_engine(self):
        response = dispatch(self.state, 'GET', '/', None)
        self.assertEqual(response.status, 200)
        self.assertIn('text/html', response.content_type)
        valuation = self.state.ledger.value(self.state.latest_date())
        self.assertIn(format(valuation.known_subtotal, 'f'), response.body)
        self.assertIn('15050', response.body)
        self.assertIn('24932.50', response.body)
        self.assertIn('synthetic', response.body.lower())
        self.assertIn('not a recommendation', response.body.lower())
        self.assertIn(ARITHMETIC_SENTENCE, response.body)
        self.assertIn('listing-currency exposure', response.body)
        self.assertNotIn('look-through', response.body.lower())
        for sentence in INTELLIGENCE:
            self.assertIn(sentence, response.body)
        self.assertIn('synthetic-price-northline-0331', response.body)
        self.assertIn('synthetic-fx-usd-nok-0331', response.body)
        self.assertNotIn('synthetic-fx-usd-nok-0218', response.body)
        self.assertIn('href="/ledger"', response.body)
        self.assertIn('href="/transactions"', response.body)
        desk_source = (ROOT / 'src' / 'huginn_muninn' / 'desk.py').read_text(
            encoding='utf-8',
        )
        for literal in _LOCKED_LITERALS:
            self.assertNotIn(literal, desk_source)

    def test_waveform_script_omits_fixture_literals_and_stays_in_directory(self):
        script_path = ROOT / 'static' / 'desk' / 'waveform.js'
        script = script_path.read_text(encoding='utf-8')
        for literal in _LOCKED_LITERALS:
            self.assertNotIn(literal, script)
        self.assertNotIn('recognized', script.lower())
        self.assertNotIn('voice model', script.lower())
        self.assertIn('getUserMedia', script)
        self.assertIn('createAnalyser', script)
        served = dispatch(self.state, 'GET', '/static/desk/waveform.js', None)
        self.assertEqual(served.status, 200)
        self.assertEqual(served.body, script)
        escaped = dispatch(
            self.state,
            'GET',
            '/static/desk/../../src/huginn_muninn/ledger.py',
            None,
        )
        self.assertEqual(escaped.status, 400)
        self.assertNotIn('class Ledger', escaped.body)
        encoded = dispatch(
            self.state,
            'GET',
            '/static/desk/%2e%2e/%2e%2e/src/huginn_muninn/ledger.py',
            None,
        )
        self.assertEqual(encoded.status, 400)
        self.assertNotIn('def performance', encoded.body)

    def test_conversation_refuses_advice_and_states_the_speech_limit(self):
        page = dispatch(self.state, 'GET', '/conversation', None)
        self.assertEqual(page.status, 200)
        self.assertIn(
            'No audio input. Speech recognition is not implemented.',
            page.body,
        )
        self.assertIn('Use microphone', page.body)
        self.assertIn('Speech synthesis is not implemented.', page.body)
        self.assertIn('/static/desk/waveform.js', page.body)
        advice = dispatch(
            self.state,
            'POST',
            '/conversation',
            {'text': 'should I buy northline?'},
        )
        reply = _last_reply(advice.body)
        self.assertIn('This desk does not recommend a transaction.', reply)
        self.assertIn(ARITHMETIC_SENTENCE, reply)
        self.assertNotIn('northline', reply.lower())
        self.assertNotIn('harbor', reply.lower())
        self.assertNotRegex(reply.lower(), r'\bbuy\b')
        self.assertNotRegex(reply.lower(), r'\bsell\b')
        sell = dispatch(
            self.state,
            'POST',
            '/conversation',
            {'text': 'please sell harbor'},
        )
        sell_reply = _last_reply(sell.body)
        self.assertIn('This desk does not recommend a transaction.', sell_reply)
        self.assertNotIn('harbor', sell_reply.lower())
        valuation = self.state.ledger.value(self.state.latest_date())
        total = dispatch(
            self.state,
            'POST',
            '/conversation',
            {'text': 'what is the total?'},
        )
        total_reply = _last_reply(total.body)
        self.assertIn(format(valuation.known_subtotal, 'f'), total_reply)
        self.assertIn('complete', total_reply.lower())
        allocation = compare(valuation, _targets(), _listings())
        gaps = dispatch(
            self.state,
            'POST',
            '/conversation',
            {'text': 'show the allocation'},
        )
        gap_reply = _last_reply(gaps.body)
        self.assertIn(ARITHMETIC_SENTENCE, gap_reply)
        for row in allocation.rows:
            if row.illustrative_amount is None:
                continue
            self.assertIn(format(row.illustrative_amount, 'f'), gap_reply)
        other = dispatch(
            self.state,
            'POST',
            '/conversation',
            {'text': 'what is the weather?'},
        )
        other_reply = _last_reply(other.body)
        self.assertIn('loaded books', other_reply)
        self.assertIn('was not one of those', other_reply)

    def test_reset_returns_the_desk_and_ledger_route_remains(self):
        response = dispatch(self.state, 'POST', '/reset', {})
        self.assertEqual(response.status, 200)
        self.assertIn('listing-currency exposure', response.body)
        self.assertIn('24932.50', response.body)
        ledger = dispatch(self.state, 'GET', '/ledger', None)
        self.assertEqual(ledger.status, 200)
        self.assertIn('Paper ledger', ledger.body)
        self.assertIn('15050', ledger.body)
