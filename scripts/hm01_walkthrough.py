"""Synthetic walkthrough of the accepted HM-01 Portfolio API.

Every amount is synthetic. This module calls the existing Portfolio API and
Decimal only. It does not define accounts, transactions, ledgers, FX,
provenance objects, or coverage math.
"""

import sys
from decimal import Decimal
from pathlib import Path

_CHECKOUT_ROOT = Path(__file__).resolve().parent.parent
if str(_CHECKOUT_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHECKOUT_ROOT))

from src.huginn_muninn.accounting import Portfolio

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


def _absent_line(portfolio):
    flags = ' '.join(
        f'{name}={hasattr(portfolio, name)}' for name in _ABSENT_FEATURES
    )
    return f'STEP absent {flags}'


def render_walkthrough() -> str:
    """Return the human-readable demonstration, including live STEP lines."""
    lines = []
    lines.append('HM-01 synthetic portfolio walkthrough')
    lines.append('')
    lines.append('Every amount is synthetic.')
    lines.append(
        'get_total_value treats a stored Decimal as the value itself; '
        'it does not multiply quantity by price.'
    )
    lines.append(
        'This demonstration does not give investment advice, percentages, '
        'or recommendations.'
    )
    lines.append('')

    portfolio = Portfolio()
    lines.append('Empty portfolio.')
    lines.append(
        'A new portfolio has a representation-currency label, an as-of label, '
        'and no stored holdings.'
    )
    lines.append(
        'STEP representation '
        f'currency={portfolio.get_currency()} '
        f'as_of={portfolio.get_as_of()} '
        f'assets={len(portfolio.assets)}'
    )
    lines.append('')

    portfolio.add_asset('cash', Decimal('10000.00'))
    portfolio.add_asset('broad-fund', Decimal('2500.50'))
    lines.append('Two synthetic valued amounts are stored.')
    lines.append(
        'The string key cash is only a dictionary identity, not an account.'
    )
    lines.append(
        'STEP stored '
        f'cash={portfolio.get_asset("cash")} '
        f'broad-fund={portfolio.get_asset("broad-fund")}'
    )
    lines.append('')

    prior_cash = portfolio.get_asset('cash')
    portfolio.add_asset('cash', Decimal('8000.00'))
    cash_now = portfolio.get_asset('cash')
    prior_cash_retained = cash_now == prior_cash
    lines.append('add_asset replaces the stored value. There is no journal.')
    lines.append(f'The previous {prior_cash} is gone.')
    lines.append(
        'STEP overwrite '
        f'cash={cash_now} '
        f'prior_cash_retained={prior_cash_retained}'
    )
    lines.append('')

    valuation = portfolio.get_total_value()
    lines.append('Valuation of the two finite Decimals.')
    if isinstance(valuation, Decimal):
        lines.append('The returned valuation is a Decimal.')
    else:
        lines.append('The returned valuation is not a Decimal.')
    lines.append(
        'STEP valuation '
        f'known_subtotal={valuation.known_subtotal} '
        f'complete={valuation.complete} '
        f'unknown={valuation.unknown_holdings}'
    )
    lines.append('')

    portfolio.add_asset('private-note', 'synthetic-unpriced')
    portfolio.add_asset('missing-quote', None)
    incomplete = portfolio.get_total_value()
    lines.append(
        'Incomplete valuation. Both unsupported holdings stay on the portfolio.'
    )
    lines.append('get_asset still returns the stored objects.')
    lines.append(
        'STEP incomplete '
        f'known_subtotal={incomplete.known_subtotal} '
        f'complete={incomplete.complete} '
        f'unknown={incomplete.unknown_holdings} '
        f'retained_private={portfolio.get_asset("private-note")} '
        f'retained_missing={portfolio.get_asset("missing-quote")}'
    )
    lines.append('')

    portfolio.set_as_of('2025-01-01')
    cash_still = portfolio.get_asset('cash')
    reconstructed = cash_still == Decimal('10000.00')
    lines.append('Changing the as-of label does not rewind the overwritten cash.')
    lines.append('historical reconstruction is not implemented.')
    lines.append(
        'STEP history '
        f'as_of_label={portfolio.get_as_of()} '
        f'cash_still={cash_still} '
        f'reconstructed={reconstructed}'
    )
    lines.append('')

    subtotal_before_label = portfolio.get_total_value().known_subtotal
    portfolio.set_currency('USD')
    labeled = portfolio.get_total_value()
    converted = labeled.known_subtotal != subtotal_before_label
    lines.append('Currency is a label. No conversion is applied.')
    lines.append(
        'STEP currency_label '
        f'currency={portfolio.get_currency()} '
        f'known_subtotal={labeled.known_subtotal} '
        f'converted={converted}'
    )
    lines.append('')

    lines.append(
        'Non-finite limitation, shown on two fresh portfolios so the results '
        'do not hide each other.'
    )
    lines.append('non-finite Decimal values still count as known.')
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
    lines.append('')

    lines.append(
        'The API does not provide accounts, transactions, cash flows, '
        'reconciliation, provenance, conversion, historical replay, coverage, '
        'or advice.'
    )
    lines.append(_absent_line(portfolio))
    lines.append('')
    return '\n'.join(lines)


def main() -> int:
    print(render_walkthrough(), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
