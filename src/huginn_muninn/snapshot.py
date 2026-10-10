from decimal import Decimal
from typing import NamedTuple


_REASON_ORDER = (
    'missing_amount',
    'non_decimal',
    'non_finite',
    'currency_mismatch',
    'as_of_mismatch',
    'missing_provenance',
)


class Holding(NamedTuple):
    """One synthetic holding. Fields are stored as given."""

    identity: object
    amount: object
    currency: object
    as_of: object
    provenance: object


class Exclusion(NamedTuple):
    """A retained holding that did not enter the known subtotal."""

    identity: object
    reasons: tuple


class Qualification(NamedTuple):
    """Known finite subtotal and every excluded holding, in insertion order."""

    known_subtotal: Decimal
    complete: bool
    excluded: tuple


class Snapshot:
    """Separate synthetic snapshot. This type does not replace Portfolio."""

    def __init__(self, reporting_currency, valuation_date):
        self.reporting_currency = reporting_currency
        self.valuation_date = valuation_date
        self.holdings = []

    def add_holding(self, holding):
        if not isinstance(holding, Holding):
            raise TypeError('add_holding requires a Holding')
        self.holdings.append(holding)

    def qualify(self):
        known_subtotal = Decimal(0)
        excluded = []
        for holding in self.holdings:
            reasons = _reasons(
                holding,
                self.reporting_currency,
                self.valuation_date,
            )
            if reasons:
                excluded.append(Exclusion(holding.identity, reasons))
            else:
                known_subtotal += holding.amount
        excluded_rows = tuple(excluded)
        return Qualification(known_subtotal, not excluded_rows, excluded_rows)


def _reasons(holding, reporting_currency, valuation_date):
    flagged = set()
    amount = holding.amount
    if amount is None:
        flagged.add('missing_amount')
    elif not isinstance(amount, Decimal):
        flagged.add('non_decimal')
    elif not amount.is_finite():
        flagged.add('non_finite')
    if holding.currency != reporting_currency:
        flagged.add('currency_mismatch')
    if holding.as_of != valuation_date:
        flagged.add('as_of_mismatch')
    provenance = holding.provenance
    if not isinstance(provenance, str) or len(provenance) == 0:
        flagged.add('missing_provenance')
    return tuple(reason for reason in _REASON_ORDER if reason in flagged)
