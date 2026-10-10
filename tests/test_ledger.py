import importlib.util
import unittest
from decimal import Decimal, getcontext
from pathlib import Path

from src.huginn_muninn.ledger import (
    Account,
    Books,
    Buy,
    CashBalance,
    Deposit,
    Dividend,
    FxRate,
    Instrument,
    Ledger,
    PortfolioValuation,
    Position,
    PriceObservation,
    Sell,
    Statement,
    StatementCash,
    StatementPosition,
    Withdrawal,
)
from src.huginn_muninn.snapshot import Holding, Snapshot


def _base():
    ledger = Ledger('NOK')
    ledger.add_account(Account('brokerage'))
    ledger.add_instrument(Instrument('fund-nok', 'NOK'))
    ledger.add_instrument(Instrument('fund-usd', 'USD'))
    return ledger


def _events():
    return (
        Deposit(
            'dep-1',
            'brokerage',
            'NOK',
            Decimal('10000'),
            '2026-01-01',
            'synthetic-deposit',
        ),
        Buy(
            'buy-nok',
            'brokerage',
            'fund-nok',
            Decimal('10'),
            'NOK',
            Decimal('5000'),
            Decimal('10'),
            '2026-01-02',
            'synthetic-buy-nok',
        ),
        Dividend(
            'div-1',
            'brokerage',
            'fund-nok',
            'NOK',
            Decimal('25'),
            '2026-01-03',
            'synthetic-dividend',
        ),
        Sell(
            'sell-nok',
            'brokerage',
            'fund-nok',
            Decimal('4'),
            'NOK',
            Decimal('2200'),
            Decimal('5'),
            '2026-01-04',
            'synthetic-sell',
        ),
        Buy(
            'buy-usd',
            'brokerage',
            'fund-usd',
            Decimal('2'),
            'NOK',
            Decimal('300'),
            Decimal('0'),
            '2026-01-05',
            'synthetic-buy-usd',
        ),
    )


def _story():
    ledger = _base()
    for event in _events():
        posting = ledger.record(event)
        if not posting.accepted:
            raise AssertionError(posting)
    return ledger


def _observe(
    ledger,
    *,
    nok_price=True,
    usd_price=True,
    rate=True,
    nok_valuation='2026-01-05',
    nok_evidence='2026-01-05',
):
    if nok_price:
        accepted = ledger.add_price(
            PriceObservation(
                'px-fund-nok',
                'fund-nok',
                Decimal('520'),
                'NOK',
                nok_valuation,
                nok_evidence,
                'synthetic-price-nok',
            )
        )
        if not accepted.accepted:
            raise AssertionError(accepted)
    if usd_price:
        accepted = ledger.add_price(
            PriceObservation(
                'px-fund-usd',
                'fund-usd',
                Decimal('20'),
                'USD',
                '2026-01-05',
                '2026-01-05',
                'synthetic-price-usd',
            )
        )
        if not accepted.accepted:
            raise AssertionError(accepted)
    if rate:
        accepted = ledger.add_rate(
            FxRate(
                'fx-usd-nok',
                'USD',
                'NOK',
                Decimal('10.5'),
                '2026-01-05',
                '2026-01-05',
                'synthetic-fx',
            )
        )
        if not accepted.accepted:
            raise AssertionError(accepted)
    return ledger


def _statement(cash_amount, statement_id):
    return Statement(
        statement_id,
        'brokerage',
        '2026-01-05',
        'synthetic-statement',
        (StatementCash('NOK', cash_amount),),
        (
            StatementPosition('fund-nok', Decimal('6')),
            StatementPosition('fund-usd', Decimal('2')),
        ),
    )


def _line(valuation, identity):
    matches = [line for line in valuation.lines if line.identity == identity]
    if len(matches) != 1:
        raise AssertionError(valuation.lines)
    return matches[0]


def _load_walkthrough():
    script_path = (
        Path(__file__).resolve().parent.parent
        / 'scripts'
        / 'accounting_walkthrough.py'
    )
    spec = importlib.util.spec_from_file_location(
        'accounting_walkthrough',
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {script_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LedgerStoryTest(unittest.TestCase):
    def test_five_events_replay_historical_books(self):
        reporting = 'NOK'
        ledger = Ledger(reporting)
        self.assertIs(ledger.reporting_currency, reporting)
        ledger.add_account(Account('brokerage'))
        ledger.add_instrument(Instrument('fund-nok', 'NOK'))
        ledger.add_instrument(Instrument('fund-usd', 'USD'))
        postings = [ledger.record(event) for event in _events()]
        self.assertTrue(all(posting.accepted for posting in postings))
        self.assertTrue(all(posting.reasons == () for posting in postings))

        opened = ledger.books('2026-01-01')
        self.assertEqual(
            opened.cash,
            (CashBalance('brokerage', 'NOK', Decimal('10000')),),
        )
        self.assertEqual(opened.positions, ())
        self.assertEqual(opened.applied_event_ids, ('dep-1',))

        after_buy = ledger.books('2026-01-02')
        self.assertEqual(
            after_buy,
            Books(
                '2026-01-02',
                (CashBalance('brokerage', 'NOK', Decimal('4990')),),
                (Position('brokerage', 'fund-nok', Decimal('10')),),
                ('dep-1', 'buy-nok'),
            ),
        )
        self.assertEqual(ledger.books('2026-01-02'), after_buy)

        after_dividend = ledger.books('2026-01-03')
        self.assertEqual(
            after_dividend.positions,
            (Position('brokerage', 'fund-nok', Decimal('10')),),
        )
        self.assertEqual(after_dividend.cash[0].amount, Decimal('5015'))

        after_sell = ledger.books('2026-01-04')
        self.assertEqual(after_sell.cash[0].amount, Decimal('7210'))
        self.assertEqual(
            after_sell.positions,
            (Position('brokerage', 'fund-nok', Decimal('6')),),
        )

        final = ledger.books('2026-01-05')
        self.assertEqual(
            final.cash,
            (CashBalance('brokerage', 'NOK', Decimal('6910')),),
        )
        self.assertEqual(
            final.positions,
            (
                Position('brokerage', 'fund-nok', Decimal('6')),
                Position('brokerage', 'fund-usd', Decimal('2')),
            ),
        )
        self.assertEqual(
            final.applied_event_ids,
            ('dep-1', 'buy-nok', 'div-1', 'sell-nok', 'buy-usd'),
        )

    def test_later_events_are_absent_from_an_earlier_date(self):
        ledger = _story()
        self.assertEqual(
            ledger.books('2026-01-01').applied_event_ids,
            ('dep-1',),
        )
        self.assertNotIn('buy-nok', ledger.books('2026-01-01').applied_event_ids)


class LedgerRejectionTest(unittest.TestCase):
    def test_overspend_is_rejected_and_books_stay_put(self):
        ledger = _story()
        before = ledger.books('2026-01-05')
        withdrawal = ledger.record(
            Withdrawal(
                'wd-too-much',
                'brokerage',
                'NOK',
                Decimal('6911'),
                '2026-01-06',
                'synthetic-withdrawal',
            )
        )
        self.assertFalse(withdrawal.accepted)
        self.assertEqual(withdrawal.reasons, ('insufficient_cash',))
        buy = ledger.record(
            Buy(
                'buy-too-much',
                'brokerage',
                'fund-nok',
                Decimal('1'),
                'NOK',
                Decimal('6910'),
                Decimal('1'),
                '2026-01-06',
                'synthetic-buy-too-much',
            )
        )
        self.assertEqual(buy.reasons, ('insufficient_cash',))
        later = ledger.books('2026-01-06')
        self.assertEqual(later.cash, before.cash)
        self.assertEqual(later.positions, before.positions)
        self.assertEqual(later.applied_event_ids, before.applied_event_ids)
        self.assertEqual(ledger.books('2026-01-05'), before)

    def test_oversell_does_not_reduce_quantity(self):
        ledger = _story()
        before = ledger.books('2026-01-05')
        posting = ledger.record(
            Sell(
                'sell-too-much',
                'brokerage',
                'fund-nok',
                Decimal('7'),
                'NOK',
                Decimal('100'),
                Decimal('0'),
                '2026-01-06',
                'synthetic-oversell',
            )
        )
        self.assertEqual(posting.reasons, ('insufficient_quantity',))
        later = ledger.books('2026-01-06')
        self.assertEqual(later.cash, before.cash)
        self.assertEqual(later.positions, before.positions)
        self.assertEqual(later.positions[0].quantity, Decimal('6'))
        self.assertEqual(later.applied_event_ids, before.applied_event_ids)

    def test_non_finite_and_integer_amounts_are_not_applied(self):
        ledger = _base()
        opening = ledger.record(
            Deposit(
                'dep-1',
                'brokerage',
                'NOK',
                Decimal('10000'),
                '2026-01-01',
                'synthetic-deposit',
            )
        )
        self.assertTrue(opening.accepted)
        before = ledger.books('2026-01-02')
        cases = (
            ('nan', Decimal('NaN')),
            ('inf', Decimal('Infinity')),
            ('ninf', Decimal('-Infinity')),
        )
        for event_id, amount in cases:
            posting = ledger.record(
                Deposit(
                    event_id,
                    'brokerage',
                    'NOK',
                    amount,
                    '2026-01-02',
                    'synthetic-bad-amount',
                )
            )
            self.assertEqual(posting.reasons, ('non_finite',))
            quantity = ledger.record(
                Buy(
                    f'qty-{event_id}',
                    'brokerage',
                    'fund-nok',
                    amount,
                    'NOK',
                    Decimal('1'),
                    Decimal('0'),
                    '2026-01-02',
                    'synthetic-bad-quantity',
                )
            )
            self.assertIn('non_finite', quantity.reasons)
        integer = ledger.record(
            Deposit(
                'integer',
                'brokerage',
                'NOK',
                10000,
                '2026-01-02',
                'synthetic-integer',
            )
        )
        self.assertEqual(integer.reasons, ('non_decimal',))
        self.assertNotIsInstance(10000, Decimal)
        self.assertEqual(ledger.books('2026-01-02'), before)
        self.assertEqual(before.cash[0].amount, Decimal('10000'))

    def test_blank_provenance_is_not_applied(self):
        ledger = _base()
        for event_id, provenance in (('space', ' '), ('empty', '')):
            posting = ledger.record(
                Deposit(
                    event_id,
                    'brokerage',
                    'NOK',
                    Decimal('10000'),
                    '2026-01-01',
                    provenance,
                )
            )
            self.assertEqual(posting.reasons, ('blank_provenance',))
        self.assertEqual(ledger.books('2026-01-01').cash, ())
        kept = Deposit(
            'kept',
            'brokerage',
            'NOK',
            Decimal('3'),
            '2026-01-01',
            ' synthetic ',
        )
        self.assertTrue(ledger.record(kept).accepted)
        self.assertEqual(kept.provenance, ' synthetic ')

    def test_backdated_event_is_not_applied(self):
        ledger = _story()
        before = ledger.books('2026-01-05')
        posting = ledger.record(
            Deposit(
                'backdated',
                'brokerage',
                'NOK',
                Decimal('1'),
                '2026-01-04',
                'synthetic-backdated',
            )
        )
        self.assertEqual(posting.reasons, ('out_of_order',))
        self.assertEqual(ledger.books('2026-01-05'), before)
        self.assertNotIn('backdated', ledger.books('2026-01-05').applied_event_ids)

    def test_same_date_is_allowed_and_duplicate_id_is_not(self):
        ledger = _base()
        first = ledger.record(
            Deposit(
                'same',
                'brokerage',
                'NOK',
                Decimal('1'),
                '2026-01-05',
                'synthetic',
            )
        )
        second = ledger.record(
            Deposit(
                'same-day',
                'brokerage',
                'NOK',
                Decimal('2'),
                '2026-01-05',
                'synthetic',
            )
        )
        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        duplicate = ledger.record(
            Deposit(
                'same',
                'brokerage',
                'NOK',
                Decimal('4'),
                '2026-01-05',
                'synthetic',
            )
        )
        self.assertEqual(duplicate.reasons, ('duplicate_id',))
        self.assertEqual(
            ledger.books('2026-01-05').cash[0].amount,
            Decimal('3'),
        )

    def test_several_event_reasons_keep_contract_order(self):
        ledger = _base()
        posting = ledger.record(
            Buy(
                'mixed',
                'missing-account',
                'missing-fund',
                5,
                'NOK',
                Decimal('-1'),
                Decimal('NaN'),
                'not-a-date',
                ' ',
            )
        )
        self.assertEqual(
            posting.reasons,
            (
                'unknown_account',
                'unknown_instrument',
                'invalid_date',
                'blank_provenance',
                'non_decimal',
                'non_finite',
                'negative_amount',
            ),
        )
        self.assertEqual(ledger.books('2026-01-01').applied_event_ids, ())

    def test_sell_shortfall_and_dividend_without_position(self):
        ledger = _base()
        ledger.record(
            Deposit(
                'dep',
                'brokerage',
                'NOK',
                Decimal('100'),
                '2026-01-01',
                'synthetic',
            )
        )
        dividend = ledger.record(
            Dividend(
                'div',
                'brokerage',
                'fund-nok',
                'NOK',
                Decimal('1'),
                '2026-01-02',
                'synthetic',
            )
        )
        self.assertEqual(dividend.reasons, ('no_position',))
        bought = ledger.record(
            Buy(
                'buy',
                'brokerage',
                'fund-nok',
                Decimal('1'),
                'NOK',
                Decimal('40'),
                Decimal('0'),
                '2026-01-02',
                'synthetic',
            )
        )
        self.assertTrue(bought.accepted)
        posting = ledger.record(
            Sell(
                'sell',
                'brokerage',
                'fund-nok',
                Decimal('5'),
                'NOK',
                Decimal('0'),
                Decimal('80'),
                '2026-01-03',
                'synthetic',
            )
        )
        self.assertEqual(
            posting.reasons,
            ('insufficient_cash', 'insufficient_quantity'),
        )
        self.assertEqual(
            ledger.books('2026-01-03').positions[0].quantity,
            Decimal('1'),
        )
        self.assertEqual(
            ledger.books('2026-01-03').cash[0].amount,
            Decimal('60'),
        )


class LedgerValuationTest(unittest.TestCase):
    def test_complete_valuation_cites_price_and_directed_rate(self):
        ledger = _observe(_story())
        before = ledger.books('2026-01-05')
        valuation = ledger.value('2026-01-05')
        self.assertEqual(ledger.books('2026-01-05'), before)
        self.assertIsInstance(valuation, PortfolioValuation)
        self.assertEqual(valuation.known_subtotal, Decimal('10450'))
        self.assertTrue(valuation.complete)
        cash = _line(valuation, 'NOK')
        nok_fund = _line(valuation, 'fund-nok')
        usd_fund = _line(valuation, 'fund-usd')
        self.assertEqual(cash.kind, 'cash')
        self.assertEqual(cash.quantity_or_amount, Decimal('6910'))
        self.assertEqual(cash.reporting_amount, Decimal('6910'))
        self.assertIsNone(cash.price_id)
        self.assertIsNone(cash.rate_id)
        self.assertEqual(cash.reasons, ())
        self.assertEqual(nok_fund.kind, 'position')
        self.assertEqual(nok_fund.quantity_or_amount, Decimal('6'))
        self.assertEqual(nok_fund.reporting_amount, Decimal('3120'))
        self.assertEqual(nok_fund.price_id, 'px-fund-nok')
        self.assertIsNone(nok_fund.rate_id)
        self.assertEqual(usd_fund.quantity_or_amount, Decimal('2'))
        self.assertEqual(usd_fund.reporting_amount, Decimal('420'))
        self.assertEqual(usd_fund.price_id, 'px-fund-usd')
        self.assertEqual(usd_fund.rate_id, 'fx-usd-nok')
        self.assertEqual(usd_fund.reasons, ())

    def test_missing_rate_excludes_the_position_without_inversion(self):
        ledger = _observe(_story(), rate=False)
        inverted = ledger.add_rate(
            FxRate(
                'fx-nok-usd',
                'NOK',
                'USD',
                Decimal('0.1'),
                '2026-01-05',
                '2026-01-05',
                'synthetic-inverted',
            )
        )
        self.assertTrue(inverted.accepted)
        valuation = ledger.value('2026-01-05')
        usd_fund = _line(valuation, 'fund-usd')
        self.assertEqual(usd_fund.reasons, ('missing_rate',))
        self.assertIsNone(usd_fund.reporting_amount)
        self.assertEqual(usd_fund.quantity_or_amount, Decimal('2'))
        self.assertIsNone(usd_fund.rate_id)
        self.assertEqual(valuation.known_subtotal, Decimal('10030'))
        self.assertFalse(valuation.complete)
        self.assertEqual(_line(valuation, 'NOK').reporting_amount, Decimal('6910'))
        self.assertEqual(
            _line(valuation, 'fund-nok').reporting_amount,
            Decimal('3120'),
        )

    def test_price_on_another_valuation_date_is_not_used(self):
        ledger = _observe(
            _story(),
            nok_valuation='2026-01-04',
            nok_evidence='2026-01-04',
        )
        valuation = ledger.value('2026-01-05')
        nok_fund = _line(valuation, 'fund-nok')
        self.assertEqual(nok_fund.reasons, ('missing_price',))
        self.assertIsNone(nok_fund.reporting_amount)
        self.assertIsNone(nok_fund.price_id)
        self.assertEqual(valuation.known_subtotal, Decimal('7330'))
        self.assertFalse(valuation.complete)

    def test_future_evidence_is_not_treated_as_missing_or_current(self):
        ledger = _observe(_story(), nok_evidence='2026-01-06')
        valuation = ledger.value('2026-01-05')
        nok_fund = _line(valuation, 'fund-nok')
        self.assertEqual(nok_fund.reasons, ('future_evidence',))
        self.assertIsNone(nok_fund.reporting_amount)
        self.assertEqual(valuation.known_subtotal, Decimal('7330'))
        self.assertFalse(valuation.complete)

    def test_two_rates_for_the_same_pair_and_date_are_ambiguous(self):
        ledger = _observe(_story())
        extra = ledger.add_rate(
            FxRate(
                'fx-usd-nok-b',
                'USD',
                'NOK',
                Decimal('11'),
                '2026-01-05',
                '2026-01-05',
                'synthetic-fx-b',
            )
        )
        self.assertTrue(extra.accepted)
        valuation = ledger.value('2026-01-05')
        usd_fund = _line(valuation, 'fund-usd')
        self.assertEqual(usd_fund.reasons, ('ambiguous_rate',))
        self.assertIsNone(usd_fund.reporting_amount)
        self.assertIsNone(usd_fund.rate_id)
        self.assertEqual(usd_fund.price_id, 'px-fund-usd')
        self.assertEqual(valuation.known_subtotal, Decimal('10030'))
        self.assertFalse(valuation.complete)

    def test_future_rate_does_not_outrank_one_current_rate(self):
        ledger = _observe(_story())
        future = ledger.add_rate(
            FxRate(
                'fx-later',
                'USD',
                'NOK',
                Decimal('99'),
                '2026-01-05',
                '2026-01-06',
                'synthetic-future-fx',
            )
        )
        self.assertTrue(future.accepted)
        valuation = ledger.value('2026-01-05')
        usd_fund = _line(valuation, 'fund-usd')
        self.assertEqual(usd_fund.reasons, ())
        self.assertEqual(usd_fund.rate_id, 'fx-usd-nok')
        self.assertEqual(valuation.known_subtotal, Decimal('10450'))

    def test_only_future_rates_are_future_evidence(self):
        ledger = _observe(_story(), rate=False)
        ledger.add_rate(
            FxRate(
                'fx-a',
                'USD',
                'NOK',
                Decimal('10'),
                '2026-01-05',
                '2026-01-06',
                'synthetic-a',
            )
        )
        ledger.add_rate(
            FxRate(
                'fx-b',
                'USD',
                'NOK',
                Decimal('11'),
                '2026-01-05',
                '2026-01-07',
                'synthetic-b',
            )
        )
        usd_fund = _line(ledger.value('2026-01-05'), 'fund-usd')
        self.assertEqual(usd_fund.reasons, ('future_evidence',))
        self.assertIsNone(usd_fund.reporting_amount)

    def test_foreign_cash_uses_one_directed_rate(self):
        ledger = _base()
        ledger.record(
            Deposit(
                'usd-cash',
                'brokerage',
                'USD',
                Decimal('8'),
                '2026-01-05',
                'synthetic-usd-cash',
            )
        )
        missing = ledger.value('2026-01-05')
        self.assertEqual(_line(missing, 'USD').reasons, ('missing_rate',))
        self.assertIsNone(_line(missing, 'USD').reporting_amount)
        self.assertEqual(missing.known_subtotal, Decimal('0'))
        self.assertFalse(missing.complete)
        ledger.add_rate(
            FxRate(
                'fx-usd-nok',
                'USD',
                'NOK',
                Decimal('10.5'),
                '2026-01-05',
                '2026-01-04',
                'synthetic-fx',
            )
        )
        valued = ledger.value('2026-01-05')
        cash = _line(valued, 'USD')
        self.assertEqual(cash.reporting_amount, Decimal('84'))
        self.assertIsNone(cash.price_id)
        self.assertEqual(cash.rate_id, 'fx-usd-nok')
        self.assertTrue(valued.complete)

    def test_currency_mismatch_price_is_stored_and_excluded(self):
        ledger = _story()
        posting = ledger.add_price(
            PriceObservation(
                'px-wrong',
                'fund-nok',
                Decimal('520'),
                'USD',
                '2026-01-05',
                '2026-01-05',
                'synthetic-mismatch',
            )
        )
        self.assertTrue(posting.accepted)
        valuation = ledger.value('2026-01-05')
        nok_fund = _line(valuation, 'fund-nok')
        self.assertEqual(nok_fund.reasons, ('currency_mismatch',))
        self.assertIsNone(nok_fund.reporting_amount)
        self.assertEqual(nok_fund.price_id, 'px-wrong')

    def test_empty_book_is_complete_zero(self):
        ledger = Ledger('NOK')
        valuation = ledger.value('2026-01-05')
        self.assertEqual(valuation.known_subtotal, Decimal(0))
        self.assertTrue(valuation.complete)
        self.assertEqual(valuation.lines, ())

    def test_zero_price_is_known_and_a_blank_rate_is_not_stored(self):
        ledger = _base()
        ledger.record(
            Deposit(
                'dep',
                'brokerage',
                'NOK',
                Decimal('5'),
                '2026-01-01',
                'synthetic',
            )
        )
        ledger.record(
            Buy(
                'buy',
                'brokerage',
                'fund-nok',
                Decimal('2'),
                'NOK',
                Decimal('0'),
                Decimal('0'),
                '2026-01-02',
                'synthetic',
            )
        )
        zero_price = ledger.add_price(
            PriceObservation(
                'px-zero',
                'fund-nok',
                Decimal('0'),
                'NOK',
                '2026-01-02',
                '2026-01-02',
                'synthetic-zero',
            )
        )
        self.assertTrue(zero_price.accepted)
        blank_rate = ledger.add_rate(
            FxRate(
                'fx-blank',
                'USD',
                'NOK',
                Decimal('10'),
                '2026-01-02',
                '2026-01-02',
                ' ',
            )
        )
        self.assertEqual(blank_rate.reasons, ('blank_provenance',))
        valuation = ledger.value('2026-01-02')
        self.assertEqual(_line(valuation, 'fund-nok').reporting_amount, Decimal('0'))
        self.assertTrue(valuation.complete)
        self.assertEqual(valuation.known_subtotal, Decimal('5'))

    def test_listing_currency_price_ignores_same_date_wrong_currency(self):
        ledger = _story()
        wrong = ledger.add_price(
            PriceObservation(
                'px-wrong',
                'fund-nok',
                Decimal('999'),
                'USD',
                '2026-01-05',
                '2026-01-05',
                'synthetic-wrong-currency',
            )
        )
        right = ledger.add_price(
            PriceObservation(
                'px-right',
                'fund-nok',
                Decimal('520'),
                'NOK',
                '2026-01-05',
                '2026-01-05',
                'synthetic-listing-currency',
            )
        )
        self.assertTrue(wrong.accepted)
        self.assertTrue(right.accepted)
        line = _line(ledger.value('2026-01-05'), 'fund-nok')
        self.assertEqual(line.reasons, ())
        self.assertEqual(line.price_id, 'px-right')
        self.assertEqual(line.reporting_amount, Decimal('3120'))
        self.assertNotIn('ambiguous_price', line.reasons)

    def test_two_listing_currency_prices_are_ambiguous(self):
        ledger = _story()
        ledger.add_price(
            PriceObservation(
                'px-a',
                'fund-nok',
                Decimal('520'),
                'NOK',
                '2026-01-05',
                '2026-01-05',
                'synthetic-price-a',
            )
        )
        ledger.add_price(
            PriceObservation(
                'px-b',
                'fund-nok',
                Decimal('530'),
                'NOK',
                '2026-01-05',
                '2026-01-05',
                'synthetic-price-b',
            )
        )
        line = _line(ledger.value('2026-01-05'), 'fund-nok')
        self.assertEqual(line.reasons, ('ambiguous_price',))
        self.assertIsNone(line.reporting_amount)
        self.assertIsNone(line.price_id)
        self.assertNotEqual(line.reporting_amount, Decimal('3120'))
        self.assertNotEqual(line.reporting_amount, Decimal('3180'))

    def test_two_wrong_currency_prices_are_currency_mismatch(self):
        ledger = _story()
        ledger.add_price(
            PriceObservation(
                'px-early',
                'fund-nok',
                Decimal('10'),
                'USD',
                '2026-01-05',
                '2026-01-05',
                'synthetic-early',
            )
        )
        ledger.add_price(
            PriceObservation(
                'px-late',
                'fund-nok',
                Decimal('11'),
                'EUR',
                '2026-01-05',
                '2026-01-05',
                'synthetic-late',
            )
        )
        line = _line(ledger.value('2026-01-05'), 'fund-nok')
        self.assertEqual(line.reasons, ('currency_mismatch',))
        self.assertIsNone(line.reporting_amount)
        self.assertEqual(line.price_id, 'px-early')
        self.assertNotIn('ambiguous_price', line.reasons)

    def test_lowered_caller_precision_does_not_round_the_valuation_product(self):
        ledger = _base()
        ledger.record(
            Deposit(
                'dep',
                'brokerage',
                'NOK',
                Decimal('1'),
                '2026-01-01',
                'synthetic',
            )
        )
        ledger.record(
            Buy(
                'buy',
                'brokerage',
                'fund-nok',
                Decimal('1000000'),
                'NOK',
                Decimal('0'),
                Decimal('0'),
                '2026-01-02',
                'synthetic',
            )
        )
        ledger.add_price(
            PriceObservation(
                'px-wide',
                'fund-nok',
                Decimal('1.23456789'),
                'NOK',
                '2026-01-02',
                '2026-01-02',
                'synthetic-wide',
            )
        )
        expected = Decimal('1000000') * Decimal('1.23456789')
        self.assertGreater(len(expected.as_tuple().digits), 6)
        original = getcontext().prec
        getcontext().prec = 6
        try:
            valuation = ledger.value('2026-01-02')
            self.assertEqual(
                _line(valuation, 'fund-nok').reporting_amount,
                expected,
            )
            self.assertEqual(getcontext().prec, 6)
        finally:
            getcontext().prec = original
        self.assertEqual(getcontext().prec, original)
        before = getcontext().prec
        ledger.value('2026-01-02')
        self.assertEqual(getcontext().prec, before)


class LedgerReconciliationTest(unittest.TestCase):
    def test_matching_statement_reconciles(self):
        ledger = _story()
        before = ledger.books('2026-01-05')
        result = ledger.reconcile(_statement(Decimal('6910'), 'stmt-match'))
        self.assertTrue(result.reconciled)
        self.assertEqual(result.breaks, ())
        self.assertEqual(result.statement_id, 'stmt-match')
        scaled = ledger.reconcile(_statement(Decimal('6910.00'), 'stmt-scale'))
        self.assertTrue(scaled.reconciled)
        omitted_zero = ledger.reconcile(
            Statement(
                'stmt-zero',
                'brokerage',
                '2026-01-05',
                'synthetic-statement',
                (
                    StatementCash('NOK', Decimal('6910')),
                    StatementCash('USD', Decimal('0')),
                ),
                (
                    StatementPosition('fund-nok', Decimal('6')),
                    StatementPosition('fund-usd', Decimal('2')),
                ),
            )
        )
        self.assertTrue(omitted_zero.reconciled)
        self.assertEqual(ledger.books('2026-01-05'), before)

    def test_cash_mismatch_reports_both_amounts_without_editing_books(self):
        ledger = _story()
        before = ledger.books('2026-01-05')
        result = ledger.reconcile(_statement(Decimal('6911'), 'stmt-off'))
        self.assertFalse(result.reconciled)
        self.assertEqual(len(result.breaks), 1)
        cash_break = result.breaks[0]
        self.assertEqual(cash_break.kind, 'cash')
        self.assertEqual(cash_break.identity, 'NOK')
        self.assertEqual(cash_break.book_amount, Decimal('6910'))
        self.assertEqual(cash_break.statement_amount, Decimal('6911'))
        self.assertEqual(cash_break.reasons, ('amount_mismatch',))
        self.assertEqual(ledger.books('2026-01-05'), before)
        self.assertEqual(before.cash[0].amount, Decimal('6910'))

    def test_missing_statement_position_is_a_break(self):
        ledger = _story()
        result = ledger.reconcile(
            Statement(
                'stmt-missing',
                'brokerage',
                '2026-01-05',
                'synthetic-statement',
                (StatementCash('NOK', Decimal('6910')),),
                (StatementPosition('fund-nok', Decimal('6')),),
            )
        )
        self.assertFalse(result.reconciled)
        self.assertEqual(result.breaks[0].kind, 'position')
        self.assertEqual(result.breaks[0].identity, 'fund-usd')
        self.assertEqual(result.breaks[0].book_amount, Decimal('2'))
        self.assertIsNone(result.breaks[0].statement_amount)
        self.assertEqual(result.breaks[0].reasons, ('missing_on_statement',))
        extra = ledger.reconcile(
            Statement(
                'stmt-extra',
                'brokerage',
                '2026-01-05',
                'synthetic-statement',
                (StatementCash('NOK', Decimal('6910')),),
                (
                    StatementPosition('fund-nok', Decimal('6')),
                    StatementPosition('fund-usd', Decimal('2')),
                    StatementPosition('fund-extra', Decimal('1')),
                ),
            )
        )
        self.assertFalse(extra.reconciled)
        extra_break = extra.breaks[0]
        self.assertEqual(extra_break.identity, 'fund-extra')
        self.assertIsNone(extra_break.book_amount)
        self.assertEqual(extra_break.statement_amount, Decimal('1'))
        self.assertEqual(extra_break.reasons, ('missing_in_books',))

    def test_bad_statement_header_does_not_compare_rows(self):
        ledger = _story()
        result = ledger.reconcile(
            Statement(
                'stmt-bad',
                'missing',
                'not-a-date',
                ' \t',
                (StatementCash('NOK', Decimal('1')),),
                (),
            )
        )
        self.assertFalse(result.reconciled)
        self.assertEqual(
            result.breaks[0].reasons,
            ('unknown_account', 'invalid_date', 'blank_provenance'),
        )
        self.assertEqual(ledger.books('2026-01-05').cash[0].amount, Decimal('6910'))

    def test_non_finite_statement_amount_does_not_match(self):
        ledger = _story()
        result = ledger.reconcile(_statement(Decimal('NaN'), 'stmt-nan'))
        self.assertFalse(result.reconciled)
        self.assertEqual(result.breaks[0].reasons, ('non_finite',))
        self.assertEqual(result.breaks[0].book_amount, Decimal('6910'))
        integer = ledger.reconcile(_statement(6910, 'stmt-int'))
        self.assertEqual(integer.breaks[0].reasons, ('non_decimal',))

    def test_duplicate_cash_rows_break_even_when_amounts_match(self):
        ledger = _story()
        before = ledger.books('2026-01-05')
        result = ledger.reconcile(
            Statement(
                'stmt-dup',
                'brokerage',
                '2026-01-05',
                'synthetic-statement',
                (
                    StatementCash('NOK', Decimal('6910')),
                    StatementCash('NOK', Decimal('6910')),
                ),
                (
                    StatementPosition('fund-nok', Decimal('6')),
                    StatementPosition('fund-usd', Decimal('2')),
                ),
            )
        )
        self.assertFalse(result.reconciled)
        self.assertEqual(len(result.breaks), 1)
        cash_break = result.breaks[0]
        self.assertEqual(cash_break.kind, 'cash')
        self.assertEqual(cash_break.identity, 'NOK')
        self.assertEqual(cash_break.reasons, ('duplicate_statement_row',))
        self.assertEqual(cash_break.book_amount, Decimal('6910'))
        self.assertIsNone(cash_break.statement_amount)
        self.assertEqual(ledger.books('2026-01-05'), before)

    def test_wrong_type_row_is_not_a_typed_duplicate(self):
        ledger = _story()
        result = ledger.reconcile(
            Statement(
                'stmt-type',
                'brokerage',
                '2026-01-05',
                'synthetic-statement',
                (
                    StatementCash('NOK', Decimal('6910')),
                    StatementPosition('NOK', Decimal('6910')),
                ),
                (
                    StatementPosition('fund-nok', Decimal('6')),
                    StatementPosition('fund-usd', Decimal('2')),
                ),
            )
        )
        self.assertFalse(result.reconciled)
        self.assertEqual(result.breaks[0].reasons, ('non_decimal',))
        self.assertEqual(len(result.breaks), 1)


class LedgerContractTest(unittest.TestCase):
    def test_identity_registration_does_not_coerce(self):
        ledger = Ledger('NOK')
        with self.assertRaises(TypeError):
            ledger.add_account('brokerage')
        with self.assertRaises(ValueError):
            ledger.add_account(Account(''))
        with self.assertRaises(TypeError):
            ledger.add_instrument(('fund-nok', 'NOK'))
        ledger.add_account(Account('brokerage'))
        with self.assertRaises(ValueError):
            ledger.add_account(Account('brokerage'))
        with self.assertRaises(TypeError):
            ledger.record(('dep', 'brokerage', 'NOK', Decimal('1'), '2026-01-01', 'x'))
        with self.assertRaises(ValueError):
            ledger.books('2026-02-31')
        with self.assertRaises(ValueError):
            ledger.value(None)

    def test_qualify_value_and_books_do_not_change_decimal_precision(self):
        precision = getcontext().prec
        ledger = _observe(_story())
        ledger.books('2026-01-05')
        ledger.value('2026-01-05')
        portfolio_snapshot = Snapshot('NOK', '2026-10-06')
        portfolio_snapshot.qualify()
        self.assertEqual(getcontext().prec, precision)

    def test_snapshot_space_remains_nonempty_provenance(self):
        ledger = _base()
        posting = ledger.record(
            Deposit(
                'space',
                'brokerage',
                'NOK',
                Decimal('1'),
                '2026-01-01',
                ' ',
            )
        )
        self.assertEqual(posting.reasons, ('blank_provenance',))
        portfolio_snapshot = Snapshot('NOK', '2026-10-06')
        portfolio_snapshot.add_holding(
            Holding('cash', Decimal('1'), 'NOK', '2026-10-06', ' ')
        )
        qualification = portfolio_snapshot.qualify()
        self.assertTrue(qualification.complete)
        self.assertEqual(qualification.known_subtotal, Decimal('1'))
        self.assertEqual(qualification.excluded, ())

    def test_walkthrough_prints_live_figures(self):
        text = _load_walkthrough().render_walkthrough()
        self.assertIsInstance(text, str)
        self.assertIn('synthetic', text.lower())
        self.assertIn('not a recommendation', text.lower())
        self.assertIn('books 2026-01-01 cash NOK 10000', text)
        self.assertIn('books 2026-01-05 cash NOK 6910', text)
        self.assertIn('fund-nok 6', text)
        self.assertIn('fund-usd 2', text)
        self.assertIn('valuation complete=True subtotal=10450', text)
        self.assertIn('valuation complete=False subtotal=10030', text)
        self.assertIn('reporting_amount=None', text)
        self.assertIn('reconciled=True', text)
        self.assertIn('reconciled=False', text)
        self.assertIn('book=6910', text)
        self.assertIn('statement=6911', text)


class LedgerWalkthroughEntryTest(unittest.TestCase):
    def test_main_prints_the_rendered_trace(self):
        import io
        from contextlib import redirect_stdout

        module = _load_walkthrough()
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            module.main()
        self.assertEqual(buffer.getvalue(), module.render_walkthrough() + '\n')
