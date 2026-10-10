from decimal import Decimal
from typing import NamedTuple


class Valuation(NamedTuple):
    """Known Decimal subtotal and whether that numeric valuation is complete.

    known_subtotal sums stored Decimal holdings only. An empty portfolio
    yields Decimal(0). complete is true only when every stored holding is
    a Decimal. unknown_holdings names retained missing, non-Decimal, or
    otherwise non-Decimal holdings; those holdings stay in the portfolio.

    complete does not certify currency compatibility, as-of checks,
    per-holding provenance, conversion, or valuation, exposure, or
    analytical coverage. Those qualifications are unfinished.
    """

    known_subtotal: Decimal
    complete: bool
    unknown_holdings: tuple


class Portfolio:
    def __init__(self):
        self.assets = {}
        self.currency = 'NOK'
        self.as_of = '2026-10-06'

    def add_asset(self, path, content):
        self.assets[path] = content

    def get_asset(self, path):
        return self.assets.get(path, None)

    def get_total_value(self):
        known_subtotal = Decimal(0)
        unknown_holdings = []
        for identity, holding in self.assets.items():
            if isinstance(holding, Decimal):
                known_subtotal += holding
            else:
                unknown_holdings.append(identity)
        return Valuation(
            known_subtotal,
            not unknown_holdings,
            tuple(unknown_holdings),
        )

    def get_currency(self):
        return self.currency

    def get_as_of(self):
        return self.as_of

    def set_currency(self, currency):
        self.currency = currency

    def set_as_of(self, as_of):
        self.as_of = as_of

    def __str__(self):
        valuation = self.get_total_value()
        return (
            f'Portfolio(known_subtotal={valuation.known_subtotal}, '
            f'complete={valuation.complete}, '
            f'unknown_holdings={valuation.unknown_holdings}, '
            f'currency={self.get_currency()}, as_of={self.get_as_of()})'
        )
