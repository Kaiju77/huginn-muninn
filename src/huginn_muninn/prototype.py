"""Local synthetic paper ledger.

The page loads inputs and calls Ledger. Posting, valuation, and
reconciliation stay in the ledger.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit
import json

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
    Withdrawal,
)


class Response(NamedTuple):
    status: int
    content_type: str
    body: str


_CONTENT_TYPE = 'text/html; charset=utf-8'

_CSS = """
body {
  margin: 0;
  background: #E7EEF2;
  color: #14202B;
  font-family: "Palatino Linotype", Palatino, "Iowan Old Style", Georgia, serif;
  font-size: 1.0625rem;
  line-height: 1.5;
}
main {
  width: min(46rem, calc(100% - 1.5rem));
  margin: 1.25rem auto 3rem;
  overflow-x: auto;
}
h1 {
  font-weight: normal;
  font-size: 1.8rem;
  line-height: 1.2;
  margin: 0.4rem 0 1rem;
}
h2 {
  font-weight: normal;
  font-size: 1.25rem;
  margin: 1.2rem 0 0.2rem;
}
p {
  max-width: 38rem;
}
nav a {
  margin: 0 0.9rem 0.4rem 0;
  display: inline-block;
}
a {
  color: #14202B;
}
a:focus,
button:focus,
input:focus,
select:focus {
  outline: 2px solid #14202B;
  outline-offset: 3px;
}
table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  margin: 1rem 0 1.5rem;
}
th,
td {
  padding: 0.4rem 0.55rem 0.4rem 0;
  border-bottom: 1px solid #8AA0B2;
  text-align: left;
  vertical-align: baseline;
  white-space: nowrap;
}
.figure {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
  overflow-wrap: normal;
}
.running .figure {
  width: 46%;
  border-left: 1px solid #8AA0B2;
  padding-left: 0.8rem;
  font-size: 1.35rem;
}
.qualified {
  color: #0E6B4F;
}
.break {
  color: #9B2C2C;
}
label {
  display: block;
  margin-top: 0.8rem;
}
input,
select,
button {
  max-width: 100%;
  font: inherit;
  color: #14202B;
  background: #E7EEF2;
}
input,
select {
  width: 100%;
  border: 1px solid #8AA0B2;
  padding: 0.35rem 0.4rem;
}
button {
  margin-top: 0.9rem;
  border: 1px solid #14202B;
  padding: 0.35rem 0.7rem;
}
.note {
  margin-top: 2rem;
}
svg {
  width: 100%;
  height: auto;
  display: block;
}
figcaption {
  margin-top: 0.6rem;
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation: none;
    transition: none;
    scroll-behavior: auto;
  }
}
"""

_EVENT_KINDS = ('deposit', 'withdrawal', 'buy', 'sell', 'dividend')


def _require_decimal(value, label):
    """Accept a decimal string. JSON numbers and other types are refused."""
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(f'{label} must be a decimal string')
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{label} must be a decimal string') from exc


def _validate_decimals(document):
    if not isinstance(document, dict):
        raise ValueError('portfolio document must be an object')
    for key in (
        'reporting_currency',
        'accounts',
        'instruments',
        'events',
        'prices',
        'rates',
        'statements',
    ):
        if key not in document:
            raise ValueError(f'{key} is required')
    for event in document['events']:
        kind = event.get('type')
        if kind in {'deposit', 'withdrawal', 'dividend'}:
            _require_decimal(event.get('amount'), 'amount')
        elif kind in {'buy', 'sell'}:
            _require_decimal(event.get('quantity'), 'quantity')
            _require_decimal(event.get('cash_amount'), 'cash_amount')
            _require_decimal(event.get('fee'), 'fee')
        else:
            raise ValueError('event type must be deposit, withdrawal, buy, sell, or dividend')
    for price in document['prices']:
        _require_decimal(price.get('price'), 'price')
    for rate in document['rates']:
        _require_decimal(rate.get('rate'), 'rate')
    for statement in document['statements']:
        for cash in statement.get('cash', ()):
            _require_decimal(cash.get('amount'), 'amount')
        for position in statement.get('positions', ()):
            _require_decimal(position.get('quantity'), 'quantity')


def load_document(path):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    _validate_decimals(document)
    return document


def _event_from_row(row):
    kind = row['type']
    if kind == 'deposit':
        return Deposit(
            row['event_id'],
            row['account'],
            row['currency'],
            _require_decimal(row['amount'], 'amount'),
            row['event_date'],
            row['provenance'],
        )
    if kind == 'withdrawal':
        return Withdrawal(
            row['event_id'],
            row['account'],
            row['currency'],
            _require_decimal(row['amount'], 'amount'),
            row['event_date'],
            row['provenance'],
        )
    if kind == 'buy':
        return Buy(
            row['event_id'],
            row['account'],
            row['instrument'],
            _require_decimal(row['quantity'], 'quantity'),
            row['cash_currency'],
            _require_decimal(row['cash_amount'], 'cash_amount'),
            _require_decimal(row['fee'], 'fee'),
            row['event_date'],
            row['provenance'],
        )
    if kind == 'sell':
        return Sell(
            row['event_id'],
            row['account'],
            row['instrument'],
            _require_decimal(row['quantity'], 'quantity'),
            row['cash_currency'],
            _require_decimal(row['cash_amount'], 'cash_amount'),
            _require_decimal(row['fee'], 'fee'),
            row['event_date'],
            row['provenance'],
        )
    if kind == 'dividend':
        return Dividend(
            row['event_id'],
            row['account'],
            row['instrument'],
            row['currency'],
            _require_decimal(row['amount'], 'amount'),
            row['event_date'],
            row['provenance'],
        )
    raise ValueError('event type must be deposit, withdrawal, buy, sell, or dividend')


def _price_from_row(row):
    return PriceObservation(
        row['observation_id'],
        row['instrument'],
        _require_decimal(row['price'], 'price'),
        row['price_currency'],
        row['valuation_date'],
        row['evidence_date'],
        row['provenance'],
    )


def _rate_from_row(row):
    return FxRate(
        row['rate_id'],
        row['base'],
        row['quote'],
        _require_decimal(row['rate'], 'rate'),
        row['rate_date'],
        row['evidence_date'],
        row['provenance'],
    )


def _statement_from_row(row):
    cash = tuple(
        StatementCash(item['currency'], _require_decimal(item['amount'], 'amount'))
        for item in row.get('cash', ())
    )
    positions = tuple(
        StatementPosition(
            item['instrument'],
            _require_decimal(item['quantity'], 'quantity'),
        )
        for item in row.get('positions', ())
    )
    return Statement(
        row['statement_id'],
        row['account'],
        row['on_date'],
        row['provenance'],
        cash,
        positions,
    )


def _iso(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class PrototypeState:
    """Fixture or overlay, replayed through Ledger."""

    def __init__(self, fixture_path, overlay_path):
        self.fixture_path = Path(fixture_path)
        self.overlay_path = Path(overlay_path)
        self.document = None
        self.ledger = None
        self.event_postings = []
        self.price_postings = []
        self.rate_postings = []
        self.statement_results = []
        self.load()

    def load(self):
        source = self.overlay_path if self.overlay_path.is_file() else self.fixture_path
        self.document = load_document(source)
        self._replay()

    def _replay(self):
        document = self.document
        ledger = Ledger(document['reporting_currency'])
        for account in document['accounts']:
            ledger.add_account(Account(account['identity']))
        for instrument in document['instruments']:
            ledger.add_instrument(
                Instrument(instrument['identity'], instrument['listing_currency'])
            )
        events = []
        for row in document['events']:
            events.append((row, ledger.record(_event_from_row(row))))
        prices = []
        for row in document['prices']:
            prices.append((row, ledger.add_price(_price_from_row(row))))
        rates = []
        for row in document['rates']:
            rates.append((row, ledger.add_rate(_rate_from_row(row))))
        statements = []
        for row in document['statements']:
            statements.append((row, ledger.reconcile(_statement_from_row(row))))
        self.ledger = ledger
        self.event_postings = events
        self.price_postings = prices
        self.rate_postings = rates
        self.statement_results = statements

    def save(self):
        self.overlay_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.document, indent=2) + '\n'
        self.overlay_path.write_text(text, encoding='utf-8')

    def reset(self):
        if self.overlay_path.is_file():
            self.overlay_path.unlink()
        self.load()

    def submit_event(self, row):
        self.document['events'].append(row)
        self.save()
        self.load()
        return self.event_postings[-1][1]

    def submit_statement(self, row):
        existing = {
            item['statement_id'] for item in self.document['statements']
        }
        if row['statement_id'] not in existing:
            self.document['statements'].append(row)
            self.save()
            self.load()
            for stored, result in self.statement_results:
                if stored['statement_id'] == row['statement_id']:
                    return result, True
        result = self.ledger.reconcile(_statement_from_row(row))
        return result, False

    def display_name(self, identity):
        for instrument in self.document['instruments']:
            if instrument.get('identity') == identity:
                name = instrument.get('display_name')
                if isinstance(name, str) and name != '':
                    return name
        return identity

    def observation_dates(self):
        found = set()
        for row, posting in self.event_postings:
            if posting.accepted and _iso(row.get('event_date')) is not None:
                found.add(row['event_date'])
        for row, posting in self.price_postings:
            if posting.accepted and _iso(row.get('valuation_date')) is not None:
                found.add(row['valuation_date'])
        for row, posting in self.rate_postings:
            if posting.accepted and _iso(row.get('rate_date')) is not None:
                found.add(row['rate_date'])
        return tuple(sorted(found))

    def latest_date(self):
        dates = self.observation_dates()
        if not dates:
            return None
        return dates[-1]


def open_state(checkout, overlay_path=None):
    root = Path(checkout)
    fixture = root / 'fixtures' / 'synthetic_portfolio.json'
    if overlay_path is None:
        overlay_path = root / 'var' / 'synthetic-book.json'
    return PrototypeState(fixture, overlay_path)


def _field(form, name):
    if not form or name not in form:
        return ''
    value = form[name]
    if isinstance(value, (list, tuple)):
        if not value:
            return ''
        value = value[0]
    if value is None:
        return ''
    return str(value)


def _fields(form, name):
    if not form or name not in form:
        return []
    value = form[name]
    if isinstance(value, (list, tuple)):
        return ['' if item is None else str(item) for item in value]
    if value is None:
        return []
    return [str(value)]


def _checked_decimal(raw, label):
    _require_decimal(raw, label)
    return raw


def _event_from_form(form):
    kind = _field(form, 'type')
    row = {
        'type': kind,
        'event_id': _field(form, 'event_id'),
        'account': _field(form, 'account'),
        'event_date': _field(form, 'event_date'),
        'provenance': _field(form, 'provenance'),
    }
    if kind in {'deposit', 'withdrawal'}:
        row['currency'] = _field(form, 'currency')
        row['amount'] = _checked_decimal(_field(form, 'amount'), 'amount')
        return row
    if kind == 'dividend':
        row['instrument'] = _field(form, 'instrument')
        row['currency'] = _field(form, 'currency')
        row['amount'] = _checked_decimal(_field(form, 'amount'), 'amount')
        return row
    if kind in {'buy', 'sell'}:
        row['instrument'] = _field(form, 'instrument')
        row['quantity'] = _checked_decimal(_field(form, 'quantity'), 'quantity')
        row['cash_currency'] = _field(form, 'cash_currency')
        row['cash_amount'] = _checked_decimal(
            _field(form, 'cash_amount'),
            'cash_amount',
        )
        row['fee'] = _checked_decimal(_field(form, 'fee'), 'fee')
        return row
    raise ValueError(
        'type must be deposit, withdrawal, buy, sell, or dividend'
    )


def _paired_rows(form, left_name, right_name, left_label, right_label):
    lefts = _fields(form, left_name)
    rights = _fields(form, right_name)
    if len(lefts) != len(rights):
        raise ValueError(f'{left_label} and {right_label} counts differ')
    rows = []
    for left, right in zip(lefts, rights):
        if left == '' and right == '':
            continue
        if left == '' or right == '':
            raise ValueError(f'{left_label} and {right_label} are both required')
        rows.append({left_label: left, right_label: _checked_decimal(right, right_label)})
    return rows


def _statement_from_form(form):
    cash = []
    for item in _paired_rows(
        form,
        'cash_currency',
        'cash_amount',
        'currency',
        'amount',
    ):
        cash.append({'currency': item['currency'], 'amount': item['amount']})
    positions = []
    for item in _paired_rows(
        form,
        'position_instrument',
        'position_quantity',
        'instrument',
        'quantity',
    ):
        positions.append(
            {'instrument': item['instrument'], 'quantity': item['quantity']}
        )
    return {
        'statement_id': _field(form, 'statement_id'),
        'account': _field(form, 'account'),
        'on_date': _field(form, 'on_date'),
        'provenance': _field(form, 'provenance'),
        'cash': cash,
        'positions': positions,
    }


def _figure(amount):
    if amount is None:
        return ''
    if isinstance(amount, Decimal):
        if not amount.is_finite():
            return escape(str(amount))
        return escape(format(amount, 'f'))
    return escape(str(amount))


def _nav(state):
    latest = state.latest_date()
    history = '/history'
    valuation = '/valuation'
    if latest:
        history = '/history?date=' + escape(latest)
        valuation = '/valuation?date=' + escape(latest)
    return (
        '<nav>'
        '<a href="/">Books</a>'
        '<a href="/transactions">Transactions</a>'
        '<a href="/transactions/new">Record a transaction</a>'
        f'<a href="{history}">History</a>'
        f'<a href="{valuation}">Valuation</a>'
        '<a href="/reconcile">Reconciliation</a>'
        '<a href="/chart">Chart</a>'
        '</nav>'
    )


def _page(state, title, body, status=200):
    document = (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{escape(title)}</title>\n'
        '<style>\n'
        + _CSS
        + '</style>\n'
        '</head>\n'
        '<body>\n<main>\n'
        + _nav(state)
        + f'<h1>{escape(title)}</h1>\n'
        + body
        + '<p class="note">These figures are synthetic. This page is not a recommendation.</p>\n'
        '</main>\n</body>\n</html>\n'
    )
    return Response(status, _CONTENT_TYPE, document)


def _event_amount(row):
    kind = row.get('type')
    if kind in {'deposit', 'withdrawal', 'dividend'}:
        return row.get('amount', '')
    return row.get('cash_amount', '')


def _home(state):
    latest = state.latest_date()
    if latest is None:
        return _page(
            state,
            'Paper ledger',
            '<p>There is no book date in the loaded inputs.</p>',
        )
    books = state.ledger.books(latest)
    valuation = state.ledger.value(latest)
    complete = 'complete' if valuation.complete else 'incomplete'
    amount_class = 'figure qualified' if valuation.complete else 'figure'
    rows = []
    for cash in books.cash:
        figure_class = amount_class if cash.currency == state.ledger.reporting_currency else 'figure'
        rows.append(
            '<tr>'
            f'<td>Cash {escape(cash.currency)}</td>'
            f'<td class="{figure_class}">{_figure(cash.amount)}</td>'
            '</tr>'
        )
    for position in books.positions:
        rows.append(
            '<tr>'
            f'<td>{escape(state.display_name(position.instrument))}</td>'
            f'<td class="figure">{_figure(position.quantity)}</td>'
            '</tr>'
        )
    rows.append(
        '<tr>'
        '<td>Known subtotal</td>'
        f'<td class="{amount_class}">{_figure(valuation.known_subtotal)}</td>'
        '</tr>'
    )
    body = (
        f'<p>Books on {escape(latest)}. The latest valuation is {complete}.</p>'
        '<table class="ledger running"><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
        '<form method="post" action="/reset" enctype="application/x-www-form-urlencoded">'
        '<button type="submit">Reload the fixture</button>'
        '</form>'
    )
    return _page(state, 'Paper ledger', body)


def _transactions(state):
    rows = []
    for event, posting in state.event_postings:
        if posting.accepted:
            result = 'accepted'
            result_class = ''
        else:
            result = ', '.join(posting.reasons)
            result_class = ' class="break"'
        rows.append(
            '<tr>'
            f'<td>{escape(str(event.get("event_date", "")))}</td>'
            f'<td>{escape(str(event.get("type", "")))}</td>'
            f'<td>{escape(str(event.get("event_id", "")))}</td>'
            f'<td{result_class}>{escape(result)}</td>'
            f'<td class="figure">{escape(str(_event_amount(event)))}</td>'
            '</tr>'
        )
    body = (
        '<table class="ledger running"><thead><tr>'
        '<th>Date</th><th>Type</th><th>Id</th><th>Result</th>'
        '<th class="figure">Amount</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )
    return _page(state, 'Transactions', body)


def _kind_options(selected):
    parts = []
    for kind in _EVENT_KINDS:
        mark = ' selected' if kind == selected else ''
        parts.append(f'<option value="{kind}"{mark}>{kind}</option>')
    return ''.join(parts)


def _input(name, label, value=''):
    return (
        f'<label for="{name}">{escape(label)}'
        f'<input id="{name}" name="{name}" value="{escape(value)}">'
        '</label>'
    )


def _transaction_form(state, posting=None, error=None, status=200):
    parts = []
    if error:
        parts.append(f'<p class="break">{escape(error)}</p>')
    if posting is not None:
        if posting.accepted:
            parts.append(
                f'<p class="qualified">The ledger accepted {escape(posting.item_id)}.</p>'
            )
        else:
            reasons = ', '.join(posting.reasons)
            parts.append(
                '<p class="break">The ledger rejected '
                f'{escape(posting.item_id)}. Reasons: {escape(reasons)}.</p>'
            )
    parts.append(
        '<form method="post" action="/transactions" enctype="application/x-www-form-urlencoded">'
        '<label for="type">Type'
        f'<select id="type" name="type">{_kind_options("deposit")}</select>'
        '</label>'
        + _input('event_id', 'Event id')
        + _input('account', 'Account', 'brokerage')
        + _input('event_date', 'Date')
        + _input('provenance', 'Provenance')
        + _input('currency', 'Currency', 'NOK')
        + _input('amount', 'Amount')
        + _input('instrument', 'Instrument')
        + _input('quantity', 'Quantity')
        + _input('cash_currency', 'Cash currency', 'NOK')
        + _input('cash_amount', 'Cash amount')
        + _input('fee', 'Fee')
        + '<button type="submit">Record transaction</button>'
        '</form>'
    )
    return _page(state, 'Record a transaction', ''.join(parts), status)


def _date_form(action, current):
    return (
        f'<form method="get" action="{action}">'
        '<label for="date">Date'
        f'<input id="date" name="date" value="{escape(current)}">'
        '</label>'
        '<button type="submit">Show this date</button>'
        '</form>'
    )


def _history(state, query):
    day = _field(query, 'date')
    try:
        books = state.ledger.books(day)
    except ValueError as exc:
        body = f'<p class="break">{escape(str(exc))}</p>' + _date_form('/history', day)
        return _page(state, 'History', body, 400)
    rows = []
    for cash in books.cash:
        rows.append(
            '<tr>'
            f'<td>Cash {escape(cash.currency)}</td>'
            f'<td class="figure">{_figure(cash.amount)}</td>'
            '</tr>'
        )
    for position in books.positions:
        rows.append(
            '<tr>'
            f'<td>{escape(state.display_name(position.instrument))}</td>'
            f'<td class="figure">{_figure(position.quantity)}</td>'
            '</tr>'
        )
    body = (
        f'<p>Books on {escape(books.on_date)}.</p>'
        '<table class="ledger running"><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
        + _date_form('/history', day)
    )
    return _page(state, 'History', body)


def _valuation(state, query):
    day = _field(query, 'date')
    try:
        valuation = state.ledger.value(day)
    except ValueError as exc:
        body = f'<p class="break">{escape(str(exc))}</p>' + _date_form('/valuation', day)
        return _page(state, 'Valuation', body, 400)
    rows = []
    excluded = []
    for line in valuation.lines:
        reporting = _figure(line.reporting_amount)
        if line.reasons:
            excluded.append(line.identity)
        reason_text = ', '.join(line.reasons)
        rows.append(
            '<tr'
            f' data-identity="{escape(line.identity)}"'
            f' data-reporting="{reporting}"'
            f' data-reasons="{escape(reason_text)}"'
            '>'
            f'<td>{escape(line.kind)}</td>'
            f'<td>{escape(line.identity)}</td>'
            f'<td class="figure">{_figure(line.quantity_or_amount)}</td>'
            f'<td class="figure">{reporting}</td>'
            f'<td>{escape(line.price_id or "")}</td>'
            f'<td>{escape(line.rate_id or "")}</td>'
            f'<td>{escape(reason_text)}</td>'
            '</tr>'
        )
    if valuation.complete:
        summary = '<p>The valuation is complete.</p>'
    else:
        names = ', '.join(escape(identity) for identity in excluded)
        summary = (
            '<p class="break">The total is not complete. '
            f'Excluded lines: {names}.</p>'
        )
    body = (
        summary
        + '<table class="ledger"><thead><tr>'
        '<th>Kind</th><th>Identity</th><th class="figure">Source amount</th>'
        '<th class="figure">Reporting amount</th><th>Price id</th>'
        '<th>Rate id</th><th>Reasons</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
        '<table class="ledger running"><tbody><tr>'
        '<td>Known subtotal</td>'
        f'<td class="figure">{_figure(valuation.known_subtotal)}</td>'
        '</tr></tbody></table>'
        + _date_form('/valuation', day)
    )
    return _page(state, 'Valuation', body)


def _break_rows(result):
    if result.reconciled:
        return '<p class="qualified">Reconciled.</p>'
    rows = []
    for item in result.breaks:
        rows.append(
            '<tr>'
            f'<td>{escape(item.kind)}</td>'
            f'<td>{escape(item.identity)}</td>'
            f'<td class="figure">{_figure(item.book_amount)}</td>'
            f'<td class="figure">{_figure(item.statement_amount)}</td>'
            f'<td class="break">{escape(", ".join(item.reasons))}</td>'
            '</tr>'
        )
    return (
        '<p class="break">Reconciled false.</p>'
        '<table class="ledger"><thead><tr>'
        '<th>Kind</th><th>Identity</th><th class="figure">Book amount</th>'
        '<th class="figure">Statement amount</th><th>Reasons</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )


def _statement_block(row, result):
    return (
        f'<h2>{escape(row.get("statement_id", ""))}</h2>'
        f'<p>{escape(str(row.get("on_date", "")))} '
        f'{escape(str(row.get("provenance", "")))}</p>'
        + _break_rows(result)
    )


def _reconcile_form():
    return (
        '<form method="post" action="/reconcile" enctype="application/x-www-form-urlencoded">'
        + _input('statement_id', 'Statement id')
        + _input('account', 'Account', 'brokerage')
        + _input('on_date', 'Date')
        + _input('provenance', 'Provenance')
        + _repeat_pair('cash_currency', 'Cash currency', 'cash_amount', 'Cash amount')
        + _repeat_pair(
            'position_instrument',
            'Position instrument',
            'position_quantity',
            'Position quantity',
        )
        + '<button type="submit">Compare statement</button>'
        '</form>'
    )


def _repeat_pair(left_name, left_label, right_name, right_label):
    parts = []
    for index in (1, 2):
        left_id = f'{left_name}-{index}'
        right_id = f'{right_name}-{index}'
        parts.append(
            f'<label for="{left_id}">{escape(left_label)} {index}'
            f'<input id="{left_id}" name="{left_name}" value="">'
            '</label>'
            f'<label for="{right_id}">{escape(right_label)} {index}'
            f'<input id="{right_id}" name="{right_name}" value="">'
            '</label>'
        )
    return ''.join(parts)


def _reconcile_page(state, banner='', error=None, status=200):
    parts = []
    if error:
        parts.append(f'<p class="break">{escape(error)}</p>')
    if banner:
        parts.append(banner)
    for row, result in state.statement_results:
        parts.append(_statement_block(row, result))
    parts.append(_reconcile_form())
    return _page(state, 'Reconciliation', ''.join(parts), status)


def _chart_svg(points):
    opening = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 280" role="img">'
        '<title>Known subtotal</title>'
        '<line x1="40" y1="220" x2="680" y2="220" stroke="#8AA0B2" stroke-width="1"></line>'
    )
    if not points:
        return opening + '</svg>'
    amounts = [valuation.known_subtotal for _day, valuation in points]
    low = min(amounts)
    high = max(amounts)
    span = high - low
    if span == 0:
        span = Decimal(1)
    slot = Decimal(640) / Decimal(len(points))
    parts = [opening]
    for index, (day, valuation) in enumerate(points):
        ratio = (valuation.known_subtotal - low) / span
        x = Decimal(40) + (Decimal(index) + Decimal('0.5')) * slot
        y = Decimal(220) - (ratio * Decimal(160))
        subtotal = format(valuation.known_subtotal, 'f')
        complete = 'true' if valuation.complete else 'false'
        state_word = 'complete' if valuation.complete else 'incomplete'
        parts.append(
            '<g'
            f' data-date="{escape(day)}"'
            f' data-subtotal="{escape(subtotal)}"'
            f' data-complete="{complete}"'
            '>'
            f'<title>{escape(day)} {escape(subtotal)} {state_word}</title>'
        )
        if valuation.complete:
            parts.append(
                f'<circle cx="{format(x, "f")}" cy="{format(y, "f")}" r="5" fill="#0E6B4F"></circle>'
            )
        else:
            parts.append(
                '<rect'
                f' x="{format(x - Decimal(5), "f")}"'
                f' y="{format(y - Decimal(5), "f")}"'
                ' width="10" height="10" fill="#9B2C2C"></rect>'
            )
        parts.append('</g>')
    parts.append('</svg>')
    return ''.join(parts)


def _chart(state):
    points = [
        (day, state.ledger.value(day))
        for day in state.observation_dates()
    ]
    caption = 'Known subtotal'
    rows = []
    for day, valuation in points:
        status = 'complete' if valuation.complete else 'incomplete'
        figure_class = 'figure qualified' if valuation.complete else 'figure break'
        rows.append(
            '<tr>'
            f'<td>{escape(day)}</td>'
            f'<td class="{figure_class}">{_figure(valuation.known_subtotal)}</td>'
            f'<td>{status}</td>'
            '</tr>'
        )
    body = (
        '<figure>'
        + _chart_svg(points)
        + f'<figcaption>{escape(caption)}</figcaption>'
        '</figure>'
        '<table class="ledger running"><thead><tr>'
        '<th>Date</th><th class="figure">Known subtotal</th><th>Status</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )
    return _page(state, 'Chart', body)


def _post_transaction(state, form):
    try:
        row = _event_from_form(form)
    except ValueError as exc:
        return _transaction_form(state, error=str(exc), status=400)
    posting = state.submit_event(row)
    return _transaction_form(state, posting)


def _post_reconcile(state, form):
    try:
        row = _statement_from_form(form)
    except ValueError as exc:
        return _reconcile_page(state, error=str(exc), status=400)
    result, appended = state.submit_statement(row)
    note = 'Saved with the synthetic statements.' if appended else (
        'This statement id is already stored.'
    )
    banner = f'<p>{escape(note)}</p>' + _statement_block(row, result)
    return _reconcile_page(state, banner=banner)


def dispatch(state, method, path, form):
    verb = str(method or '').upper()
    parsed = urlsplit(path or '/')
    route = parsed.path or '/'
    if route != '/':
        route = route.rstrip('/') or '/'
    query = parse_qs(parsed.query, keep_blank_values=True)
    form = {} if form is None else form
    if verb == 'GET' and route == '/':
        return _home(state)
    if verb == 'GET' and route == '/transactions':
        return _transactions(state)
    if verb == 'GET' and route == '/transactions/new':
        return _transaction_form(state)
    if verb == 'POST' and route == '/transactions':
        return _post_transaction(state, form)
    if verb == 'GET' and route == '/history':
        return _history(state, query)
    if verb == 'GET' and route == '/valuation':
        return _valuation(state, query)
    if verb == 'GET' and route == '/reconcile':
        return _reconcile_page(state)
    if verb == 'POST' and route == '/reconcile':
        return _post_reconcile(state, form)
    if verb == 'GET' and route == '/chart':
        return _chart(state)
    if verb == 'POST' and route == '/reset':
        state.reset()
        return _home(state)
    known = {
        '/',
        '/transactions',
        '/transactions/new',
        '/history',
        '/valuation',
        '/reconcile',
        '/chart',
        '/reset',
    }
    if route in known:
        return _page(state, 'Method not allowed', '<p>That action is not available here.</p>', 405)
    return _page(state, 'Missing page', '<p>That page is not in this ledger.</p>', 404)
