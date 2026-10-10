import contextlib
import importlib.util
import io
import sys
import unittest
from decimal import Decimal, getcontext
from pathlib import Path


EXPECTED_STEP_LINES = (
    'STEP representation currency=NOK as_of=2026-10-06 assets=0',
    'STEP stored cash=10000.00 broad-fund=2500.50',
    'STEP overwrite cash=8000.00 prior_cash_retained=False',
    'STEP valuation known_subtotal=10500.50 complete=True unknown=()',
    (
        'STEP incomplete known_subtotal=10500.50 complete=False '
        "unknown=('private-note', 'missing-quote') "
        'retained_private=synthetic-unpriced retained_missing=None'
    ),
    'STEP history as_of_label=2025-01-01 cash_still=8000.00 reconstructed=False',
    'STEP currency_label currency=USD known_subtotal=10500.50 converted=False',
    'STEP non_finite_nan known_subtotal=NaN complete=True unknown=()',
    'STEP non_finite_infinity known_subtotal=Infinity complete=True unknown=()',
    (
        'STEP absent accounts=False transactions=False cash_flows=False '
        'reconciliation=False provenance=False conversion=False '
        'historical_replay=False coverage=False advice=False'
    ),
)

_ABSENT_FEATURES = (
    'accounts',
    'transactions',
    'cash_flows',
    'reconciliation',
    'provenance',
    'conversion',
    'historical_replay',
    'coverage',
    'advice',
)


def load_walkthrough():
    script_path = (
        Path(__file__).resolve().parent.parent / 'scripts' / 'hm01_walkthrough.py'
    )
    spec = importlib.util.spec_from_file_location('hm01_walkthrough', script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {script_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_portfolio():
    checkout = str(Path(__file__).resolve().parent.parent)
    if checkout not in sys.path:
        sys.path.insert(0, checkout)
    from src.huginn_muninn.accounting import Portfolio
    return Portfolio


def reconstruct_step_lines(Portfolio):
    """Replay the demonstration against Portfolio without reading the script."""
    portfolio = Portfolio()
    lines = [
        (
            'STEP representation '
            f'currency={portfolio.get_currency()} '
            f'as_of={portfolio.get_as_of()} '
            f'assets={len(portfolio.assets)}'
        )
    ]

    portfolio.add_asset('cash', Decimal('10000.00'))
    portfolio.add_asset('broad-fund', Decimal('2500.50'))
    lines.append(
        'STEP stored '
        f'cash={portfolio.get_asset("cash")} '
        f'broad-fund={portfolio.get_asset("broad-fund")}'
    )

    prior_cash = portfolio.get_asset('cash')
    portfolio.add_asset('cash', Decimal('8000.00'))
    cash_now = portfolio.get_asset('cash')
    lines.append(
        'STEP overwrite '
        f'cash={cash_now} '
        f'prior_cash_retained={cash_now == prior_cash}'
    )

    valuation = portfolio.get_total_value()
    lines.append(
        'STEP valuation '
        f'known_subtotal={valuation.known_subtotal} '
        f'complete={valuation.complete} '
        f'unknown={valuation.unknown_holdings}'
    )

    portfolio.add_asset('private-note', 'synthetic-unpriced')
    portfolio.add_asset('missing-quote', None)
    incomplete = portfolio.get_total_value()
    lines.append(
        'STEP incomplete '
        f'known_subtotal={incomplete.known_subtotal} '
        f'complete={incomplete.complete} '
        f'unknown={incomplete.unknown_holdings} '
        f'retained_private={portfolio.get_asset("private-note")} '
        f'retained_missing={portfolio.get_asset("missing-quote")}'
    )

    portfolio.set_as_of('2025-01-01')
    cash_still = portfolio.get_asset('cash')
    lines.append(
        'STEP history '
        f'as_of_label={portfolio.get_as_of()} '
        f'cash_still={cash_still} '
        f'reconstructed={cash_still == Decimal("10000.00")}'
    )

    subtotal_before_label = portfolio.get_total_value().known_subtotal
    portfolio.set_currency('USD')
    labeled = portfolio.get_total_value()
    lines.append(
        'STEP currency_label '
        f'currency={portfolio.get_currency()} '
        f'known_subtotal={labeled.known_subtotal} '
        f'converted={labeled.known_subtotal != subtotal_before_label}'
    )

    nan_portfolio = Portfolio()
    nan_portfolio.add_asset('cash', Decimal('10'))
    nan_portfolio.add_asset('bad', Decimal('NaN'))
    nan_valuation = nan_portfolio.get_total_value()
    lines.append(
        'STEP non_finite_nan '
        f'known_subtotal={nan_valuation.known_subtotal} '
        f'complete={nan_valuation.complete} '
        f'unknown={nan_valuation.unknown_holdings}'
    )

    infinity_portfolio = Portfolio()
    infinity_portfolio.add_asset('cash', Decimal('10'))
    infinity_portfolio.add_asset('bad', Decimal('Infinity'))
    infinity_valuation = infinity_portfolio.get_total_value()
    lines.append(
        'STEP non_finite_infinity '
        f'known_subtotal={infinity_valuation.known_subtotal} '
        f'complete={infinity_valuation.complete} '
        f'unknown={infinity_valuation.unknown_holdings}'
    )

    absent = ' '.join(
        f'{name}={hasattr(portfolio, name)}' for name in _ABSENT_FEATURES
    )
    lines.append(f'STEP absent {absent}')
    return {
        'lines': lines,
        'valuation': valuation,
        'incomplete': incomplete,
        'portfolio': portfolio,
        'nan_valuation': nan_valuation,
        'infinity_valuation': infinity_valuation,
    }


class Hm01WalkthroughTest(unittest.TestCase):
    def test_contract_step_lines_are_present(self):
        rendered_lines = load_walkthrough().render_walkthrough().splitlines()
        for line in EXPECTED_STEP_LINES:
            self.assertIn(line, rendered_lines)

    def test_required_sentences_are_present(self):
        text = load_walkthrough().render_walkthrough()
        self.assertIn('historical reconstruction is not implemented', text)
        self.assertIn('non-finite Decimal values still count as known', text)

    def test_render_walkthrough_does_not_change_decimal_precision(self):
        previous = getcontext().prec
        getcontext().prec = 12
        try:
            module = load_walkthrough()
            self.assertEqual(getcontext().prec, 12)
            module.render_walkthrough()
            self.assertEqual(getcontext().prec, 12)
        finally:
            getcontext().prec = previous

    def test_independent_reconstruction_matches_rendered_steps(self):
        Portfolio = load_portfolio()
        observed = reconstruct_step_lines(Portfolio)
        self.assertEqual(tuple(observed['lines']), EXPECTED_STEP_LINES)

        valuation = observed['valuation']
        self.assertNotIsInstance(valuation, Decimal)
        self.assertEqual(valuation.known_subtotal, Decimal('10500.50'))
        self.assertTrue(valuation.complete)
        self.assertEqual(valuation.unknown_holdings, ())

        incomplete = observed['incomplete']
        self.assertNotIsInstance(incomplete, Decimal)
        self.assertEqual(incomplete.known_subtotal, Decimal('10500.50'))
        self.assertFalse(incomplete.complete)
        self.assertEqual(
            incomplete.unknown_holdings,
            ('private-note', 'missing-quote'),
        )
        portfolio = observed['portfolio']
        self.assertEqual(portfolio.get_asset('private-note'), 'synthetic-unpriced')
        self.assertIsNone(portfolio.get_asset('missing-quote'))
        self.assertEqual(portfolio.get_asset('cash'), Decimal('8000.00'))

        nan_valuation = observed['nan_valuation']
        self.assertTrue(nan_valuation.known_subtotal.is_nan())
        self.assertTrue(nan_valuation.complete)
        self.assertEqual(nan_valuation.unknown_holdings, ())

        infinity_valuation = observed['infinity_valuation']
        self.assertTrue(infinity_valuation.known_subtotal.is_infinite())
        self.assertTrue(infinity_valuation.complete)
        self.assertEqual(infinity_valuation.unknown_holdings, ())

        rendered_lines = load_walkthrough().render_walkthrough().splitlines()
        for line in observed['lines']:
            self.assertIn(line, rendered_lines)

    def test_main_returns_zero(self):
        module = load_walkthrough()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = module.main()
        self.assertEqual(status, 0)
        self.assertIn(EXPECTED_STEP_LINES[0], stdout.getvalue().splitlines())
