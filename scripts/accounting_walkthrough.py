"""Synthetic accounting walkthrough.

Every amount is synthetic. The printed trace is not a recommendation.
"""

import sys
from decimal import Decimal
from pathlib import Path

_CHECKOUT_ROOT = Path(__file__).resolve().parent.parent
if str(_CHECKOUT_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHECKOUT_ROOT))

from src.huginn_muninn.ledger import (
    Account,
    Buy,
    Deposit,
    Dividend,
    FxRate,
    Instrument,
    Ledger,
    PriceObservation,
    Sell,
    Statement,
    StatementCash,
    StatementPosition,
)


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


def _ledger(include_rate):
    ledger = Ledger('NOK')
    ledger.add_account(Account('brokerage'))
    ledger.add_instrument(Instrument('fund-nok', 'NOK'))
    ledger.add_instrument(Instrument('fund-usd', 'USD'))
    postings = []
    for event in _events():
        postings.append(ledger.record(event))
    ledger.add_price(
        PriceObservation(
            'px-fund-nok',
            'fund-nok',
            Decimal('520'),
            'NOK',
            '2026-01-05',
            '2026-01-05',
            'synthetic-price-nok',
        )
    )
    ledger.add_price(
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
    if include_rate:
        ledger.add_rate(
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
    return ledger, postings


def _books_line(books):
    cash = ' '.join(f'{row.currency} {row.amount}' for row in books.cash) or 'none'
    positions = ' '.join(
        f'{row.instrument} {row.quantity}' for row in books.positions
    ) or 'none'
    return f'books {books.on_date} cash {cash}; positions {positions}'


def _value_line(line):
    return (
        f'{line.kind} {line.identity} '
        f'quantity_or_amount={line.quantity_or_amount} '
        f'reporting_amount={line.reporting_amount} '
        f'price_id={line.price_id} rate_id={line.rate_id}'
    )


def render_walkthrough() -> str:
    """Return the synthetic journal trace from live Ledger calls."""
    lines = [
        'Synthetic accounting ledger walkthrough',
        '',
        'Every amount is synthetic.',
        'This output is not a recommendation.',
        '',
        'Account brokerage.',
        'Instruments fund-nok listed in NOK and fund-usd listed in USD.',
        'Reporting currency NOK.',
        '',
    ]
    ledger, postings = _ledger(True)
    for event, posting in zip(_events(), postings):
        lines.append(
            f'event {event.event_id} {type(event).__name__} '
            f'date={event.event_date} accepted={posting.accepted}'
        )
    lines.append('')
    lines.append(_books_line(ledger.books('2026-01-01')))
    lines.append(_books_line(ledger.books('2026-01-05')))
    lines.append('')
    complete = ledger.value('2026-01-05')
    lines.append(
        'Complete valuation on 2026-01-05 uses the supplied USD to NOK rate.'
    )
    lines.append(
        f'valuation complete={complete.complete} subtotal={complete.known_subtotal}'
    )
    for line in complete.lines:
        lines.append(_value_line(line))
    lines.append('')
    incomplete_ledger, _postings = _ledger(False)
    incomplete = incomplete_ledger.value('2026-01-05')
    lines.append(
        'Incomplete valuation on 2026-01-05 omits the USD to NOK rate.'
    )
    lines.append(
        'No inverted NOK to USD rate is used.'
    )
    lines.append(
        f'valuation complete={incomplete.complete} '
        f'subtotal={incomplete.known_subtotal}'
    )
    for line in incomplete.lines:
        if line.reasons:
            lines.append(
                f'excluded {line.identity} reasons={",".join(line.reasons)} '
                f'reporting_amount={line.reporting_amount}'
            )
        else:
            lines.append(_value_line(line))
    lines.append('')
    matched = ledger.reconcile(
        Statement(
            'stmt-match',
            'brokerage',
            '2026-01-05',
            'synthetic-statement',
            (StatementCash('NOK', Decimal('6910')),),
            (
                StatementPosition('fund-nok', Decimal('6')),
                StatementPosition('fund-usd', Decimal('2')),
            ),
        )
    )
    mismatched = ledger.reconcile(
        Statement(
            'stmt-off',
            'brokerage',
            '2026-01-05',
            'synthetic-statement',
            (StatementCash('NOK', Decimal('6911')),),
            (
                StatementPosition('fund-nok', Decimal('6')),
                StatementPosition('fund-usd', Decimal('2')),
            ),
        )
    )
    lines.append(
        f'reconcile {matched.statement_id} reconciled={matched.reconciled}'
    )
    cash_break = mismatched.breaks[0]
    lines.append(
        f'reconcile {mismatched.statement_id} '
        f'reconciled={mismatched.reconciled} '
        f'book={cash_break.book_amount} statement={cash_break.statement_amount}'
    )
    return '\n'.join(lines)


def main():
    print(render_walkthrough())


if __name__ == '__main__':
    main()
