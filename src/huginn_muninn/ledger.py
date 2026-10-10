"""Synthetic portfolio journal.

Amounts stay Decimal values supplied by the caller. This module does not
fetch prices, invert currency pairs, or recommend a transaction.
"""

from datetime import date
from decimal import Decimal
from typing import NamedTuple


_ZERO = Decimal(0)

_REASON_ORDER = (
    'unknown_account',
    'unknown_instrument',
    'duplicate_id',
    'out_of_order',
    'invalid_date',
    'blank_provenance',
    'non_decimal',
    'non_finite',
    'non_positive',
    'negative_amount',
    'insufficient_cash',
    'insufficient_quantity',
    'no_position',
    'missing_price',
    'ambiguous_price',
    'future_evidence',
    'currency_mismatch',
    'missing_rate',
    'ambiguous_rate',
    'amount_mismatch',
    'missing_on_statement',
    'missing_in_books',
    'invalid_pair',
)


class Account(NamedTuple):
    identity: str


class Instrument(NamedTuple):
    identity: str
    listing_currency: str


class Deposit(NamedTuple):
    event_id: str
    account: str
    currency: str
    amount: object
    event_date: str
    provenance: str


class Withdrawal(NamedTuple):
    event_id: str
    account: str
    currency: str
    amount: object
    event_date: str
    provenance: str


class Buy(NamedTuple):
    event_id: str
    account: str
    instrument: str
    quantity: object
    cash_currency: str
    cash_amount: object
    fee: object
    event_date: str
    provenance: str


class Sell(NamedTuple):
    event_id: str
    account: str
    instrument: str
    quantity: object
    cash_currency: str
    cash_amount: object
    fee: object
    event_date: str
    provenance: str


class Dividend(NamedTuple):
    event_id: str
    account: str
    instrument: str
    currency: str
    amount: object
    event_date: str
    provenance: str


class PriceObservation(NamedTuple):
    observation_id: str
    instrument: str
    price: object
    price_currency: str
    valuation_date: str
    evidence_date: str
    provenance: str


class FxRate(NamedTuple):
    """Quote currency received for 1 unit of base currency.

    USD base and NOK quote stores NOK per USD. It does not create the
    opposite pair.
    """

    rate_id: str
    base: str
    quote: str
    rate: object
    rate_date: str
    evidence_date: str
    provenance: str


class StatementCash(NamedTuple):
    currency: str
    amount: object


class StatementPosition(NamedTuple):
    instrument: str
    quantity: object


class Statement(NamedTuple):
    statement_id: str
    account: str
    on_date: str
    provenance: str
    cash: tuple
    positions: tuple


class Posting(NamedTuple):
    accepted: bool
    item_id: str
    reasons: tuple


class CashBalance(NamedTuple):
    account: str
    currency: str
    amount: Decimal


class Position(NamedTuple):
    account: str
    instrument: str
    quantity: Decimal


class Books(NamedTuple):
    on_date: str
    cash: tuple
    positions: tuple
    applied_event_ids: tuple


class ValuedLine(NamedTuple):
    kind: str
    account: str
    identity: str
    quantity_or_amount: Decimal
    reporting_amount: object
    price_id: object
    rate_id: object
    reasons: tuple


class PortfolioValuation(NamedTuple):
    on_date: str
    known_subtotal: Decimal
    complete: bool
    lines: tuple


class Break(NamedTuple):
    kind: str
    identity: str
    book_amount: object
    statement_amount: object
    reasons: tuple


class Reconciliation(NamedTuple):
    statement_id: str
    reconciled: bool
    breaks: tuple


_EVENTS = (Deposit, Withdrawal, Buy, Sell, Dividend)
_INSTRUMENT_EVENTS = (Buy, Sell, Dividend)


def _ordered(flagged):
    return tuple(reason for reason in _REASON_ORDER if reason in flagged)


def _meaningful_provenance(value):
    return isinstance(value, str) and value.strip() != ''


def _as_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _decimal_reasons(value, mode):
    """Return amount reasons without coercing value.

    mode 'positive' requires a finite Decimal strictly above zero.
    mode 'nonnegative' requires a finite Decimal of zero or above.
    """
    if not isinstance(value, Decimal):
        return {'non_decimal'}
    if not value.is_finite():
        return {'non_finite'}
    if mode == 'positive' and not value > _ZERO:
        return {'non_positive'}
    if mode == 'nonnegative' and value < _ZERO:
        return {'negative_amount'}
    return set()


def _add_amount(balances, key, delta):
    if key in balances:
        balances[key] = balances[key] + delta
    elif delta != _ZERO:
        balances[key] = delta


def _apply(cash, positions, event):
    if isinstance(event, Deposit):
        _add_amount(cash, (event.account, event.currency), event.amount)
    elif isinstance(event, Withdrawal):
        _add_amount(cash, (event.account, event.currency), -event.amount)
    elif isinstance(event, Buy):
        _add_amount(
            cash,
            (event.account, event.cash_currency),
            -(event.cash_amount + event.fee),
        )
        _add_amount(
            positions,
            (event.account, event.instrument),
            event.quantity,
        )
    elif isinstance(event, Sell):
        _add_amount(
            positions,
            (event.account, event.instrument),
            -event.quantity,
        )
        _add_amount(
            cash,
            (event.account, event.cash_currency),
            event.cash_amount - event.fee,
        )
    elif isinstance(event, Dividend):
        _add_amount(cash, (event.account, event.currency), event.amount)


def _available(balances, key):
    if key in balances:
        return balances[key]
    return _ZERO


def _select(items, on_date, date_name, missing_reason, ambiguous_reason):
    eligible = []
    future = []
    for item in items:
        observed = _as_date(getattr(item, date_name))
        evidence = _as_date(item.evidence_date)
        if observed != on_date or not _meaningful_provenance(item.provenance):
            continue
        if evidence is None:
            continue
        if evidence <= on_date:
            eligible.append(item)
        else:
            future.append(item)
    if len(eligible) == 1:
        return eligible[0], set()
    if len(eligible) > 1:
        return None, {ambiguous_reason}
    if future:
        return None, {'future_evidence'}
    return None, {missing_reason}


def _nonzero_rows(mapping, row_type):
    rows = []
    for key, amount in mapping.items():
        if amount != _ZERO:
            rows.append(row_type(*key, amount))
    return tuple(rows)


class Ledger:
    """Chronological synthetic journal and reporting-currency valuation."""

    def __init__(self, reporting_currency):
        self.reporting_currency = reporting_currency
        self._accounts = {}
        self._instruments = {}
        self._accepted = []
        self._retained_events = []
        self._seen_event_ids = set()
        self._latest_accepted = None
        self._prices = []
        self._seen_price_ids = set()
        self._rates = []
        self._seen_rate_ids = set()

    def add_account(self, account):
        if not isinstance(account, Account):
            raise TypeError('add_account requires an Account')
        identity = account.identity
        if not isinstance(identity, str) or identity == '':
            raise ValueError('account identity must be a non-empty string')
        if identity in self._accounts:
            raise ValueError('duplicate account identity')
        self._accounts[identity] = account

    def add_instrument(self, instrument):
        if not isinstance(instrument, Instrument):
            raise TypeError('add_instrument requires an Instrument')
        identity = instrument.identity
        if not isinstance(identity, str) or identity == '':
            raise ValueError('instrument identity must be a non-empty string')
        if identity in self._instruments:
            raise ValueError('duplicate instrument identity')
        self._instruments[identity] = instrument

    def record(self, event):
        if not isinstance(event, _EVENTS):
            raise TypeError(
                'record requires a Deposit, Withdrawal, Buy, Sell, or Dividend'
            )
        flagged = self._event_reasons(event)
        if event.event_id not in self._seen_event_ids:
            self._seen_event_ids.add(event.event_id)
        posting = Posting(not flagged, event.event_id, _ordered(flagged))
        self._retained_events.append(event)
        if posting.accepted:
            self._accepted.append(event)
            self._latest_accepted = _as_date(event.event_date)
        return posting

    def books(self, on_date):
        parsed = _as_date(on_date)
        if parsed is None:
            raise ValueError('invalid_date')
        cash = {}
        positions = {}
        applied = []
        for event in self._accepted:
            if _as_date(event.event_date) > parsed:
                continue
            applied.append(event.event_id)
            _apply(cash, positions, event)
        return Books(
            on_date,
            _nonzero_rows(cash, CashBalance),
            _nonzero_rows(positions, Position),
            tuple(applied),
        )

    def add_price(self, observation):
        if not isinstance(observation, PriceObservation):
            raise TypeError('add_price requires a PriceObservation')
        flagged = set()
        if observation.instrument not in self._instruments:
            flagged.add('unknown_instrument')
        if observation.observation_id in self._seen_price_ids:
            flagged.add('duplicate_id')
        if _as_date(observation.valuation_date) is None or _as_date(
            observation.evidence_date
        ) is None:
            flagged.add('invalid_date')
        if not _meaningful_provenance(observation.provenance):
            flagged.add('blank_provenance')
        flagged.update(_decimal_reasons(observation.price, 'nonnegative'))
        posting = Posting(
            not flagged,
            observation.observation_id,
            _ordered(flagged),
        )
        if observation.observation_id not in self._seen_price_ids:
            self._seen_price_ids.add(observation.observation_id)
        if posting.accepted:
            self._prices.append(observation)
        return posting

    def add_rate(self, rate):
        if not isinstance(rate, FxRate):
            raise TypeError('add_rate requires an FxRate')
        flagged = set()
        if rate.rate_id in self._seen_rate_ids:
            flagged.add('duplicate_id')
        if _as_date(rate.rate_date) is None or _as_date(rate.evidence_date) is None:
            flagged.add('invalid_date')
        if not _meaningful_provenance(rate.provenance):
            flagged.add('blank_provenance')
        flagged.update(_decimal_reasons(rate.rate, 'positive'))
        if (
            not isinstance(rate.base, str)
            or not isinstance(rate.quote, str)
            or rate.base == ''
            or rate.quote == ''
            or rate.base == rate.quote
        ):
            flagged.add('invalid_pair')
        posting = Posting(not flagged, rate.rate_id, _ordered(flagged))
        if rate.rate_id not in self._seen_rate_ids:
            self._seen_rate_ids.add(rate.rate_id)
        if posting.accepted:
            self._rates.append(rate)
        return posting

    def value(self, on_date):
        snapshot = self.books(on_date)
        on = _as_date(on_date)
        lines = []
        for row in snapshot.cash:
            lines.append(self._value_cash(row, on))
        for row in snapshot.positions:
            lines.append(self._value_position(row, on))
        total = _ZERO
        complete = True
        for line in lines:
            if line.reasons:
                complete = False
            else:
                total = total + line.reporting_amount
        return PortfolioValuation(on_date, total, complete, tuple(lines))

    def reconcile(self, statement):
        if not isinstance(statement, Statement):
            raise TypeError('reconcile requires a Statement')
        flagged = set()
        if statement.account not in self._accounts:
            flagged.add('unknown_account')
        if _as_date(statement.on_date) is None:
            flagged.add('invalid_date')
        if not _meaningful_provenance(statement.provenance):
            flagged.add('blank_provenance')
        if flagged:
            statement_break = Break(
                'statement',
                statement.statement_id,
                None,
                None,
                _ordered(flagged),
            )
            return Reconciliation(statement.statement_id, False, (statement_break,))
        snapshot = self.books(statement.on_date)
        book_cash = {
            row.currency: row.amount
            for row in snapshot.cash
            if row.account == statement.account
        }
        book_positions = {
            row.instrument: row.quantity
            for row in snapshot.positions
            if row.account == statement.account
        }
        breaks = []
        breaks.extend(
            _compare_side(
                'cash',
                book_cash,
                statement.cash,
                StatementCash,
                'currency',
                'amount',
            )
        )
        breaks.extend(
            _compare_side(
                'position',
                book_positions,
                statement.positions,
                StatementPosition,
                'instrument',
                'quantity',
            )
        )
        break_rows = tuple(breaks)
        return Reconciliation(statement.statement_id, not break_rows, break_rows)

    def _state(self):
        cash = {}
        positions = {}
        for event in self._accepted:
            _apply(cash, positions, event)
        return cash, positions

    def _event_reasons(self, event):
        flagged = set()
        account_known = event.account in self._accounts
        if not account_known:
            flagged.add('unknown_account')
        instrument_known = True
        if isinstance(event, _INSTRUMENT_EVENTS):
            instrument_known = event.instrument in self._instruments
            if not instrument_known:
                flagged.add('unknown_instrument')
        if event.event_id in self._seen_event_ids:
            flagged.add('duplicate_id')
        event_day = _as_date(event.event_date)
        if event_day is None:
            flagged.add('invalid_date')
        elif (
            self._latest_accepted is not None
            and event_day < self._latest_accepted
        ):
            flagged.add('out_of_order')
        if not _meaningful_provenance(event.provenance):
            flagged.add('blank_provenance')
        cash, positions = self._state()
        self._amount_reasons(
            event,
            flagged,
            cash,
            positions,
            account_known,
            instrument_known,
        )
        return flagged

    def _amount_reasons(
        self,
        event,
        flagged,
        cash,
        positions,
        account_known,
        instrument_known,
    ):
        if isinstance(event, (Deposit, Withdrawal, Dividend)):
            amount_reasons = _decimal_reasons(event.amount, 'positive')
            flagged.update(amount_reasons)
            amount_ok = not amount_reasons
        else:
            amount_ok = False
        if isinstance(event, (Buy, Sell)):
            quantity_reasons = _decimal_reasons(event.quantity, 'positive')
            cash_reasons = _decimal_reasons(event.cash_amount, 'nonnegative')
            fee_reasons = _decimal_reasons(event.fee, 'nonnegative')
            flagged.update(quantity_reasons)
            flagged.update(cash_reasons)
            flagged.update(fee_reasons)
            quantity_ok = not quantity_reasons
            cash_ok = not cash_reasons and not fee_reasons
        else:
            quantity_ok = False
            cash_ok = False
        if isinstance(event, Withdrawal) and account_known and amount_ok:
            available = _available(cash, (event.account, event.currency))
            if available < event.amount:
                flagged.add('insufficient_cash')
        if isinstance(event, Buy) and account_known and cash_ok:
            required = event.cash_amount + event.fee
            available = _available(cash, (event.account, event.cash_currency))
            if available < required:
                flagged.add('insufficient_cash')
        if isinstance(event, Sell):
            if account_known and instrument_known and quantity_ok:
                held = _available(positions, (event.account, event.instrument))
                if event.quantity > held:
                    flagged.add('insufficient_quantity')
            if account_known and cash_ok:
                net = event.cash_amount - event.fee
                if net < _ZERO:
                    available = _available(
                        cash,
                        (event.account, event.cash_currency),
                    )
                    if available < -net:
                        flagged.add('insufficient_cash')
        if isinstance(event, Dividend) and account_known and instrument_known:
            held = _available(positions, (event.account, event.instrument))
            if not held > _ZERO:
                flagged.add('no_position')

    def _rates_for(self, base, quote):
        return [
            rate
            for rate in self._rates
            if rate.base == base and rate.quote == quote
        ]

    def _value_cash(self, row, on_date):
        if row.currency == self.reporting_currency:
            return ValuedLine(
                'cash',
                row.account,
                row.currency,
                row.amount,
                row.amount,
                None,
                None,
                (),
            )
        rate, flagged = _select(
            self._rates_for(row.currency, self.reporting_currency),
            on_date,
            'rate_date',
            'missing_rate',
            'ambiguous_rate',
        )
        if flagged:
            return ValuedLine(
                'cash',
                row.account,
                row.currency,
                row.amount,
                None,
                None,
                None,
                _ordered(flagged),
            )
        return ValuedLine(
            'cash',
            row.account,
            row.currency,
            row.amount,
            row.amount * rate.rate,
            None,
            rate.rate_id,
            (),
        )

    def _value_position(self, row, on_date):
        instrument = self._instruments[row.instrument]
        prices = [
            price
            for price in self._prices
            if price.instrument == row.instrument
        ]
        price, flagged = _select(
            prices,
            on_date,
            'valuation_date',
            'missing_price',
            'ambiguous_price',
        )
        if flagged:
            return ValuedLine(
                'position',
                row.account,
                row.instrument,
                row.quantity,
                None,
                None,
                None,
                _ordered(flagged),
            )
        if price.price_currency != instrument.listing_currency:
            return ValuedLine(
                'position',
                row.account,
                row.instrument,
                row.quantity,
                None,
                price.observation_id,
                None,
                ('currency_mismatch',),
            )
        market = row.quantity * price.price
        if instrument.listing_currency == self.reporting_currency:
            return ValuedLine(
                'position',
                row.account,
                row.instrument,
                row.quantity,
                market,
                price.observation_id,
                None,
                (),
            )
        rate, rate_flags = _select(
            self._rates_for(
                instrument.listing_currency,
                self.reporting_currency,
            ),
            on_date,
            'rate_date',
            'missing_rate',
            'ambiguous_rate',
        )
        if rate_flags:
            return ValuedLine(
                'position',
                row.account,
                row.instrument,
                row.quantity,
                None,
                price.observation_id,
                None,
                _ordered(rate_flags),
            )
        return ValuedLine(
            'position',
            row.account,
            row.instrument,
            row.quantity,
            market * rate.rate,
            price.observation_id,
            rate.rate_id,
            (),
        )


def _compare_side(
    kind,
    book_amounts,
    statement_rows,
    row_type,
    identity_name,
    value_name,
):
    breaks = []
    first = {}
    order = []
    if statement_rows is None:
        statement_rows = ()
    for row in statement_rows:
        if not isinstance(row, row_type):
            breaks.append(Break(kind, '', None, row, ('non_decimal',)))
            continue
        identity = getattr(row, identity_name)
        if identity not in first:
            first[identity] = getattr(row, value_name)
            order.append(identity)
    for identity, book_amount in book_amounts.items():
        if identity not in first:
            breaks.append(
                Break(
                    kind,
                    identity,
                    book_amount,
                    None,
                    ('missing_on_statement',),
                )
            )
            continue
        breaks.extend(
            _amount_break(kind, identity, book_amount, first[identity])
        )
    for identity in order:
        if identity not in book_amounts:
            breaks.extend(
                _amount_break(kind, identity, None, first[identity])
            )
    return breaks


def _amount_break(kind, identity, book_amount, statement_amount):
    if not isinstance(statement_amount, Decimal):
        reasons = ('non_decimal',)
    elif not statement_amount.is_finite():
        reasons = ('non_finite',)
    elif book_amount is None:
        if statement_amount == _ZERO:
            return []
        reasons = ('missing_in_books',)
    elif statement_amount != book_amount:
        reasons = ('amount_mismatch',)
    else:
        return []
    return [Break(kind, identity, book_amount, statement_amount, reasons)]
