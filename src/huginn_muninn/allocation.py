"""Arithmetic distance from an explicit target map.

The caller supplies the target weights and a valuation. This module does
not recommend a transaction, forecast a return, or fetch a price or rate.
"""

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import NamedTuple


_ZERO = Decimal(0)

ARITHMETIC_SENTENCE = (
    'This is the arithmetic difference from the configured target. '
    'It is not an investment recommendation.'
)

EXPOSURE_LABEL = 'listing-currency exposure'


class AllocationRow(NamedTuple):
    key: str
    kind: str
    current_amount: object
    current_weight: object
    target_weight: object
    weight_difference: object
    illustrative_amount: object
    recommendation: object


class ValuationReason(NamedTuple):
    identity: str
    reasons: tuple


class ExposureLine(NamedTuple):
    listing_currency: str
    reporting_amount: Decimal


class AllocationResult(NamedTuple):
    status: str
    sentence: str
    rows: tuple
    valuation_reasons: tuple
    exposure_label: str
    exposure: tuple
    known_subtotal: object


def _context():
    return Context(prec=28, rounding=ROUND_HALF_EVEN)


def _sum(amounts):
    total = _ZERO
    with localcontext(_context()):
        for amount in amounts:
            total = total + amount
    return total


def _line_key(line):
    if line.kind == 'cash':
        return 'cash:' + line.identity
    return line.identity


def _targets_valid(targets):
    if not isinstance(targets, dict) or not targets:
        return False
    total = _ZERO
    for key, weight in targets.items():
        if not isinstance(key, str) or key == '':
            return False
        if isinstance(weight, bool) or not isinstance(weight, Decimal):
            return False
        if not weight.is_finite():
            return False
        total = total + weight
    return total == Decimal('1')


def _valuation_reasons(valuation):
    reasons = []
    for line in valuation.lines:
        if line.reasons:
            reasons.append(ValuationReason(line.identity, tuple(line.reasons)))
    return tuple(reasons)


def _exposure(valuation, listing_currencies):
    listings = {} if listing_currencies is None else listing_currencies
    buckets = {}
    order = []
    for line in valuation.lines:
        if line.reasons or not isinstance(line.reporting_amount, Decimal):
            continue
        if line.kind == 'cash':
            currency = line.identity
        elif line.kind == 'position':
            currency = listings.get(line.identity)
            if not isinstance(currency, str) or currency == '':
                continue
        else:
            continue
        if currency not in buckets:
            buckets[currency] = []
            order.append(currency)
        buckets[currency].append(line.reporting_amount)
    return tuple(
        ExposureLine(currency, _sum(buckets[currency]))
        for currency in order
    )


def _grouped(valuation):
    amounts = {}
    order = []
    for line in valuation.lines:
        key = _line_key(line)
        if key not in amounts:
            amounts[key] = []
            order.append(key)
        amounts[key].append(line.reporting_amount)
    return order, {key: _sum(values) for key, values in amounts.items()}


def _gap_row(key, amount, target, known_subtotal):
    with localcontext(_context()):
        illustrative = target * known_subtotal - amount
        if known_subtotal == _ZERO:
            weight = None
            difference = None
        else:
            weight = amount / known_subtotal
            difference = target - weight
    return AllocationRow(
        key,
        'arithmetic_gap',
        amount,
        weight,
        target,
        difference,
        illustrative,
        None,
    )


def _untargeted_row(key, amount, known_subtotal):
    if known_subtotal == _ZERO:
        weight = None
    else:
        with localcontext(_context()):
            weight = amount / known_subtotal
    return AllocationRow(
        key,
        'untargeted',
        amount,
        weight,
        None,
        None,
        None,
        None,
    )


def compare(valuation, targets, listing_currencies):
    """Compare one valuation with caller-supplied Decimal weights.

    Weights must sum to Decimal('1'). A missing book row becomes zero only
    when the valuation is complete. A missing market amount is not a zero
    weight. Exposure is listing-currency exposure, with no target of its own.
    """
    reasons = _valuation_reasons(valuation)
    exposure = _exposure(valuation, listing_currencies)
    if not _targets_valid(targets):
        return AllocationResult(
            'invalid_targets',
            ARITHMETIC_SENTENCE,
            (),
            reasons,
            EXPOSURE_LABEL,
            exposure,
            valuation.known_subtotal,
        )
    if not valuation.complete:
        return AllocationResult(
            'incomplete',
            ARITHMETIC_SENTENCE,
            (),
            reasons,
            EXPOSURE_LABEL,
            exposure,
            valuation.known_subtotal,
        )
    order, totals = _grouped(valuation)
    rows = []
    for key, target in targets.items():
        if key in totals:
            amount = totals[key]
        else:
            amount = _ZERO
        rows.append(_gap_row(key, amount, target, valuation.known_subtotal))
    for key in order:
        if key in targets:
            continue
        rows.append(
            _untargeted_row(key, totals[key], valuation.known_subtotal)
        )
    return AllocationResult(
        'complete',
        ARITHMETIC_SENTENCE,
        tuple(rows),
        reasons,
        EXPOSURE_LABEL,
        exposure,
        valuation.known_subtotal,
    )
