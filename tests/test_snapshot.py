import unittest
from decimal import Decimal, getcontext

import src.huginn_muninn.snapshot as snapshot
from src.huginn_muninn.snapshot import Exclusion, Holding, Qualification, Snapshot


def _snapshot():
    return Snapshot('NOK', '2026-10-06')


def _holding(
    identity,
    amount,
    currency='NOK',
    as_of='2026-10-06',
    provenance='synthetic-fixture',
):
    return Holding(identity, amount, currency, as_of, provenance)


class SnapshotQualificationTest(unittest.TestCase):
    def test_empty_snapshot_is_complete_zero(self):
        reporting_currency = 'NOK'
        valuation_date = '2026-10-06'
        portfolio_snapshot = Snapshot(reporting_currency, valuation_date)
        self.assertIs(portfolio_snapshot.reporting_currency, reporting_currency)
        self.assertIs(portfolio_snapshot.valuation_date, valuation_date)
        self.assertEqual(portfolio_snapshot.holdings, [])
        qualification = portfolio_snapshot.qualify()
        self.assertIsInstance(qualification, Qualification)
        self.assertEqual(qualification.known_subtotal, Decimal(0))
        self.assertTrue(qualification.complete)
        self.assertEqual(qualification.excluded, ())

    def test_two_qualified_holdings_sum_exactly(self):
        portfolio_snapshot = _snapshot()
        portfolio_snapshot.add_holding(
            _holding('cash', Decimal('1000.10'), provenance='synthetic-fixture')
        )
        portfolio_snapshot.add_holding(
            _holding('reserve', Decimal('250.05'), provenance='synthetic-fixture')
        )
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(qualification.known_subtotal, Decimal('1250.15'))
        self.assertTrue(qualification.complete)
        self.assertEqual(qualification.excluded, ())

    def test_decimal_zero_qualifies(self):
        portfolio_snapshot = _snapshot()
        portfolio_snapshot.add_holding(_holding('zero', Decimal(0)))
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(qualification.known_subtotal, Decimal(0))
        self.assertTrue(qualification.complete)
        self.assertEqual(qualification.excluded, ())

    def test_each_defect_is_retained_and_excluded(self):
        integer_amount = 12
        text_amount = '12.00'
        cases = (
            ('missing', None, 'NOK', '2026-10-06', 'synthetic-fixture', ('missing_amount',)),
            ('text', text_amount, 'NOK', '2026-10-06', 'synthetic-fixture', ('non_decimal',)),
            (
                'integer',
                integer_amount,
                'NOK',
                '2026-10-06',
                'synthetic-fixture',
                ('non_decimal',),
            ),
            (
                'nan',
                Decimal('NaN'),
                'NOK',
                '2026-10-06',
                'synthetic-fixture',
                ('non_finite',),
            ),
            (
                'infinity',
                Decimal('Infinity'),
                'NOK',
                '2026-10-06',
                'synthetic-fixture',
                ('non_finite',),
            ),
            (
                'negative-infinity',
                Decimal('-Infinity'),
                'NOK',
                '2026-10-06',
                'synthetic-fixture',
                ('non_finite',),
            ),
            (
                'usd',
                Decimal('80.00'),
                'USD',
                '2026-10-06',
                'synthetic-fixture',
                ('currency_mismatch',),
            ),
            (
                'lowercase-nok',
                Decimal('40.00'),
                'nok',
                '2026-10-06',
                'synthetic-fixture',
                ('currency_mismatch',),
            ),
            (
                'stale',
                Decimal('50.00'),
                'NOK',
                '2026-10-05',
                'synthetic-fixture',
                ('as_of_mismatch',),
            ),
            (
                'empty-provenance',
                Decimal('60.00'),
                'NOK',
                '2026-10-06',
                '',
                ('missing_provenance',),
            ),
            (
                'missing-provenance',
                Decimal('70.00'),
                'NOK',
                '2026-10-06',
                None,
                ('missing_provenance',),
            ),
        )
        for identity, amount, currency, as_of, provenance, reasons in cases:
            with self.subTest(identity=identity):
                portfolio_snapshot = _snapshot()
                qualified = _holding('known', Decimal('10'))
                excluded = Holding(identity, amount, currency, as_of, provenance)
                portfolio_snapshot.add_holding(qualified)
                portfolio_snapshot.add_holding(excluded)
                qualification = portfolio_snapshot.qualify()
                self.assertEqual(qualification.known_subtotal, Decimal('10'))
                self.assertFalse(qualification.complete)
                self.assertEqual(
                    qualification.excluded,
                    (Exclusion(identity, reasons),),
                )
                self.assertIs(portfolio_snapshot.holdings[0], qualified)
                self.assertIs(portfolio_snapshot.holdings[1], excluded)
                self.assertIs(excluded.amount, amount)

    def test_currency_and_as_of_are_both_reported(self):
        portfolio_snapshot = _snapshot()
        holding = Holding(
            'mixed',
            Decimal('15.00'),
            'USD',
            '2026-10-05',
            'synthetic-fixture',
        )
        portfolio_snapshot.add_holding(holding)
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(
            qualification.excluded,
            (
                Exclusion(
                    'mixed',
                    ('currency_mismatch', 'as_of_mismatch'),
                ),
            ),
        )
        self.assertEqual(qualification.known_subtotal, Decimal(0))
        self.assertFalse(qualification.complete)
        self.assertIs(portfolio_snapshot.holdings[0], holding)

    def test_non_finite_currency_as_of_and_provenance_are_all_reported(self):
        portfolio_snapshot = _snapshot()
        holding = Holding('bad', Decimal('NaN'), 'USD', '2026-10-05', '')
        portfolio_snapshot.add_holding(holding)
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(
            qualification.excluded,
            (
                Exclusion(
                    'bad',
                    (
                        'non_finite',
                        'currency_mismatch',
                        'as_of_mismatch',
                        'missing_provenance',
                    ),
                ),
            ),
        )
        self.assertEqual(qualification.known_subtotal, Decimal(0))
        self.assertFalse(qualification.complete)

    def test_non_finite_values_do_not_enter_known_subtotal(self):
        portfolio_snapshot = _snapshot()
        known = _holding('known', Decimal('10'))
        nan_holding = _holding('nan', Decimal('NaN'))
        infinity = _holding('infinity', Decimal('Infinity'))
        negative_infinity = _holding('negative-infinity', Decimal('-Infinity'))
        portfolio_snapshot.add_holding(known)
        portfolio_snapshot.add_holding(nan_holding)
        portfolio_snapshot.add_holding(infinity)
        portfolio_snapshot.add_holding(negative_infinity)
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(qualification.known_subtotal, Decimal('10'))
        self.assertTrue(qualification.known_subtotal.is_finite())
        self.assertFalse(qualification.complete)
        self.assertEqual(
            qualification.excluded,
            (
                Exclusion('nan', ('non_finite',)),
                Exclusion('infinity', ('non_finite',)),
                Exclusion('negative-infinity', ('non_finite',)),
            ),
        )
        self.assertEqual(len(portfolio_snapshot.holdings), 4)
        self.assertIs(portfolio_snapshot.holdings[0], known)
        self.assertIs(portfolio_snapshot.holdings[1], nan_holding)
        self.assertIs(portfolio_snapshot.holdings[2], infinity)
        self.assertIs(portfolio_snapshot.holdings[3], negative_infinity)

    def test_qualify_keeps_holdings_in_insertion_order(self):
        portfolio_snapshot = _snapshot()
        first = _holding('known', Decimal('10'))
        second = _holding('missing', None)
        third = Holding(
            'usd',
            Decimal('4.00'),
            'USD',
            '2026-10-06',
            'synthetic-fixture',
        )
        fourth = _holding('later', Decimal('1.00'))
        portfolio_snapshot.add_holding(first)
        portfolio_snapshot.add_holding(second)
        portfolio_snapshot.add_holding(third)
        portfolio_snapshot.add_holding(fourth)
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(
            portfolio_snapshot.holdings,
            [first, second, third, fourth],
        )
        self.assertEqual(qualification.known_subtotal, Decimal('11.00'))
        self.assertEqual(
            tuple(item.identity for item in qualification.excluded),
            ('missing', 'usd'),
        )

    def test_add_holding_rejects_non_holding(self):
        portfolio_snapshot = _snapshot()
        kept = _holding('known', Decimal('10'))
        portfolio_snapshot.add_holding(kept)
        with self.assertRaises(TypeError):
            portfolio_snapshot.add_holding(('known', Decimal('10'), 'NOK', '2026-10-06', 'x'))
        with self.assertRaises(TypeError):
            portfolio_snapshot.add_holding(None)
        self.assertEqual(portfolio_snapshot.holdings, [kept])

    def test_qualify_does_not_change_global_precision(self):
        previous = getcontext().prec
        getcontext().prec = 9
        try:
            portfolio_snapshot = Snapshot('NOK', '2026-10-06')
            portfolio_snapshot.add_holding(
                Holding('alpha', Decimal('10'), 'NOK', '2026-10-06', 'synthetic-fixture')
            )
            portfolio_snapshot.add_holding(
                Holding('beta', Decimal('2.5'), 'NOK', '2026-10-06', 'synthetic-fixture')
            )
            portfolio_snapshot.add_holding(
                Holding('nan', Decimal('NaN'), 'NOK', '2026-10-06', 'synthetic-fixture')
            )
            qualification = portfolio_snapshot.qualify()
            self.assertEqual(qualification.known_subtotal, Decimal('12.5'))
            self.assertFalse(qualification.complete)
            self.assertEqual(getcontext().prec, 9)
        finally:
            getcontext().prec = previous

    def test_duplicate_identities_are_qualified_independently(self):
        portfolio_snapshot = _snapshot()
        qualified = _holding('same', Decimal('10'))
        excluded = _holding('same', None)
        portfolio_snapshot.add_holding(qualified)
        portfolio_snapshot.add_holding(excluded)
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(qualification.known_subtotal, Decimal('10'))
        self.assertFalse(qualification.complete)
        self.assertEqual(
            qualification.excluded,
            (Exclusion('same', ('missing_amount',)),),
        )
        self.assertIs(portfolio_snapshot.holdings[0], qualified)
        self.assertIs(portfolio_snapshot.holdings[1], excluded)

    def test_space_provenance_is_nonempty(self):
        portfolio_snapshot = _snapshot()
        holding = Holding('space', Decimal('10'), 'NOK', '2026-10-06', ' ')
        portfolio_snapshot.add_holding(holding)
        qualification = portfolio_snapshot.qualify()
        self.assertEqual(qualification.known_subtotal, Decimal('10'))
        self.assertTrue(qualification.complete)
        self.assertEqual(qualification.excluded, ())
        self.assertIs(portfolio_snapshot.holdings[0].provenance, holding.provenance)


class SnapshotModuleBoundaryTest(unittest.TestCase):
    def test_snapshot_module_does_not_import_portfolio(self):
        self.assertNotIn('Portfolio', snapshot.__dict__)
        self.assertNotIn('accounting', snapshot.__dict__)
