import importlib
import unittest
from decimal import Decimal, getcontext

import src.huginn_muninn.accounting as accounting
from src.huginn_muninn.accounting import Portfolio


class PortfolioKnownCasesTest(unittest.TestCase):
    def test_empty_portfolio_known_subtotal_is_zero(self):
        portfolio = Portfolio()
        valuation = portfolio.get_total_value()
        self.assertEqual(valuation.known_subtotal, Decimal(0))
        self.assertTrue(valuation.complete)
        self.assertEqual(valuation.unknown_holdings, ())
        self.assertNotEqual(valuation, Decimal(0))
        self.assertEqual(portfolio.get_currency(), 'NOK')
        self.assertEqual(portfolio.get_as_of(), '2026-10-06')

    def test_one_decimal_holding_of_1000(self):
        portfolio = Portfolio()
        portfolio.add_asset('cash', Decimal(1000))
        valuation = portfolio.get_total_value()
        self.assertEqual(valuation.known_subtotal, Decimal(1000))
        self.assertTrue(valuation.complete)
        self.assertEqual(valuation.unknown_holdings, ())
        self.assertNotIsInstance(valuation, Decimal)

    def test_portfolio_get_asset(self):
        portfolio = Portfolio()
        portfolio.add_asset('cash', Decimal(1000))
        self.assertEqual(portfolio.get_asset('cash'), Decimal(1000))

    def test_portfolio_set_currency(self):
        portfolio = Portfolio()
        portfolio.set_currency('USD')
        self.assertEqual(portfolio.get_currency(), 'USD')

    def test_portfolio_set_as_of(self):
        portfolio = Portfolio()
        portfolio.set_as_of('2026-10-07')
        self.assertEqual(portfolio.get_as_of(), '2026-10-07')

    def test_multiple_decimal_holdings_sum_exactly(self):
        portfolio = Portfolio()
        portfolio.add_asset('cash', Decimal('1500.10'))
        portfolio.add_asset('reserve', Decimal('250.20'))
        valuation = portfolio.get_total_value()
        self.assertEqual(valuation.known_subtotal, Decimal('1750.30'))
        self.assertTrue(valuation.complete)
        self.assertEqual(valuation.unknown_holdings, ())

    def test_unsupported_holding_is_retained_and_incomplete(self):
        portfolio = Portfolio()
        portfolio.add_asset('cash', Decimal(1000))
        portfolio.add_asset('unpriced_lot', 'synthetic-unsupported')
        portfolio.add_asset('missing_quote', None)
        valuation = portfolio.get_total_value()
        self.assertEqual(portfolio.get_asset('unpriced_lot'), 'synthetic-unsupported')
        self.assertIsNone(portfolio.get_asset('missing_quote'))
        self.assertEqual(
            valuation.unknown_holdings,
            ('unpriced_lot', 'missing_quote'),
        )
        self.assertEqual(valuation.known_subtotal, Decimal(1000))
        self.assertFalse(valuation.complete)
        self.assertNotEqual(valuation, Decimal(1000))
        self.assertNotIsInstance(valuation, Decimal)


class DecimalContextTest(unittest.TestCase):
    def test_module_use_does_not_change_global_precision(self):
        previous = getcontext().prec
        getcontext().prec = 9
        try:
            reloaded = importlib.reload(accounting)
            self.assertEqual(getcontext().prec, 9)
            portfolio = reloaded.Portfolio()
            portfolio.add_asset('alpha', Decimal('10'))
            portfolio.add_asset('beta', Decimal('2.5'))
            valuation = portfolio.get_total_value()
            self.assertEqual(valuation.known_subtotal, Decimal('12.5'))
            self.assertTrue(valuation.complete)
            self.assertEqual(getcontext().prec, 9)
        finally:
            getcontext().prec = previous
