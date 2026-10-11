"""Local synthetic paper ledger.

The page loads inputs and calls Ledger. Posting, valuation, and
reconciliation stay in the ledger.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path, PurePosixPath
from typing import NamedTuple
from urllib.parse import parse_qs, unquote, urlsplit
import json

from src.huginn_muninn.desk import (
    answer,
    build_payload,
    open_recorded_store,
    render_conversation,
    render_desk,
    render_evidence,
    render_message,
)
from src.huginn_muninn.evidence import Observation, visible_observations
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
from src.huginn_muninn.onboarding import (
    ACTIVITY_WORDS,
    ALLOCATION_INCOMPLETE,
    ATTRIBUTION_SENTENCE,
    ATTRIBUTION_UNAVAILABLE,
    CASH_SNAPSHOT_NOT_ADDED,
    DIVIDEND_SENTENCE,
    ENTERED_SENTENCE,
    FEE_SENTENCE,
    INCOMPLETE_IDENTIFICATION,
    KINDS,
    MISSING_PRICE_SENTENCE,
    SNAPSHOT_SENTENCE,
    SNAPSHOT_VALUE_SENTENCE,
    VALUATION_SENTENCE,
    EnteredPortfolio,
    EntryResult,
    default_book_path,
    display_activity,
    price_freshness,
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
        self.ingest_cache_dir = self.fixture_path.parent.parent / 'var' / 'ingest-cache'
        self.ingest_transport = None
        self.document = None
        self.ledger = None
        self.event_postings = []
        self.price_postings = []
        self.rate_postings = []
        self.statement_results = []
        self.turns = []
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
        """Delete the synthetic overlay only. The entered book is a different file."""
        if self.overlay_path.is_file():
            self.overlay_path.unlink()
        self.load()
        self.turns = []

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


def open_state(checkout, overlay_path=None, entered_path=None):
    root = Path(checkout)
    fixture = root / 'fixtures' / 'synthetic_portfolio.json'
    if overlay_path is None:
        overlay_path = root / 'var' / 'synthetic-book.json'
    if entered_path is None:
        entered_path = default_book_path(root)
    state = PrototypeState(fixture, overlay_path)
    state.entered = EnteredPortfolio(entered_path)
    return state


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
        '<a href="/">Desk</a>'
        '<a href="/ledger">Ledger</a>'
        '<a href="/portfolio">Portfolio</a>'
        '<a href="/transactions">Transactions</a>'
        '<a href="/transactions/new">Record a transaction</a>'
        f'<a href="{history}">History</a>'
        f'<a href="{valuation}">Valuation</a>'
        '<a href="/reconcile">Reconciliation</a>'
        '<a href="/chart">Chart</a>'
        '<a href="/conversation">Conversation</a>'
        '<a href="/evidence">Evidence</a>'
        '</nav>'
    )


def _page(state, title, body, status=200, footer=None):
    if footer is None:
        footer = (
            '<p class="note">These figures are synthetic. '
            'This page is not a recommendation.</p>\n'
        )
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
        + footer
        + '</main>\n</body>\n</html>\n'
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


def _selected_day(state, query):
    day = _field(query, 'date')
    if day == '':
        return state.latest_date()
    return day


def _desk(state, query):
    day = _selected_day(state, query)
    if not day:
        return Response(
            200,
            _CONTENT_TYPE,
            render_message(state, 'There is no book date in the loaded inputs.'),
        )
    try:
        body = render_desk(state, day)
    except ValueError as exc:
        return Response(400, _CONTENT_TYPE, render_message(state, str(exc)))
    return Response(200, _CONTENT_TYPE, body)


def _api_desk(state, query):
    day = _field(query, 'date')
    try:
        payload = build_payload(state, day)
    except ValueError as exc:
        body = json.dumps({'error': str(exc)})
        return Response(400, 'application/json; charset=utf-8', body)
    return Response(200, 'application/json; charset=utf-8', json.dumps(payload))


def _static_desk(state, route):
    prefix = '/static/desk/'
    plain = 'text/plain; charset=utf-8'
    if not route.startswith(prefix):
        return Response(404, plain, 'Missing file')
    name = unquote(route[len(prefix):])
    parts = PurePosixPath(name).parts
    if (
        name == ''
        or '\\' in name
        or name.startswith('/')
        or not parts
        or any(part in {'', '.', '..'} for part in parts)
    ):
        return Response(400, plain, 'That path is rejected.')
    base = (state.fixture_path.parent.parent / 'static' / 'desk').resolve()
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return Response(400, plain, 'That path is rejected.')
    if not candidate.is_file():
        return Response(404, plain, 'Missing file')
    script = candidate.read_text(encoding='utf-8')
    return Response(200, 'text/javascript; charset=utf-8', script)


def _evidence(state, query):
    day = _selected_day(state, query)
    if not day:
        return Response(
            200,
            _CONTENT_TYPE,
            render_message(state, 'There is no book date in the loaded inputs.'),
        )
    try:
        body = render_evidence(state, day)
    except ValueError as exc:
        return Response(400, _CONTENT_TYPE, render_message(state, str(exc)))
    return Response(200, _CONTENT_TYPE, body)


def _conversation(state):
    return Response(200, _CONTENT_TYPE, render_conversation(state))


def _post_evidence_refresh(state, form):
    start = _field(form, 'start_period')
    end = _field(form, 'end_period')
    if _iso(start) is None or _iso(end) is None or start > end:
        return Response(
            400,
            _CONTENT_TYPE,
            render_message(state, 'An explicit start_period and end_period are required.'),
        )
    from src.huginn_muninn.ingest.refresh import refresh_public

    transport = state.ingest_transport
    refresh_public(
        state.ingest_cache_dir,
        start,
        end,
        transport=transport,
        explicit_live=transport is None,
    )
    return _evidence(state, {})


def _post_conversation(state, form):
    text = _field(form, 'text')
    state.turns.append(('question', text))
    state.turns.append(('reply', answer(state, text)))
    return _conversation(state)


def _portfolio_input(form_name, name, label):
    field_id = f'portfolio-{form_name}-{name}'
    return (
        f'<label for="{field_id}">{escape(label)}'
        f'<input id="{field_id}" name="{escape(name)}" value="">'
        '</label>'
    )


def _portfolio_select(form_name, name, label, options):
    field_id = f'portfolio-{form_name}-{name}'
    rows = []
    for value, text in options:
        rows.append(
            f'<option value="{escape(value)}">{escape(text)}</option>'
        )
    return (
        f'<label for="{field_id}">{escape(label)}'
        f'<select id="{field_id}" name="{escape(name)}">'
        + ''.join(rows)
        + '</select></label>'
    )


def _account_choices(book):
    choices = [('', 'Choose an account')]
    for account in book.accounts:
        label = f"{account['institution']} {account['name']}"
        choices.append((account['identity'], label))
    return choices


def _instrument_choices(book):
    choices = [('', 'Choose an instrument')]
    for instrument in book.instruments:
        label = f"{instrument['display_name']}, {instrument['kind']}"
        choices.append((instrument['identity'], label))
    return choices


def _balance_choices(book):
    choices = [('', 'Choose cash or one instrument'), ('cash', 'Cash')]
    for instrument in book.instruments:
        label = f"{instrument['display_name']}, {instrument['kind']}"
        choices.append((instrument['identity'], label))
    return choices


def _activity_detail(row):
    activity = row['activity']
    if activity in {'contribution', 'withdrawal', 'fee', 'dividend'}:
        return f"{row['amount']} {row['currency']}"
    return (
        f"quantity {row['quantity']}, "
        f"cash {row['cash_amount']} {row['cash_currency']}, "
        f"fee {row['fee']}"
    )


def _result_banner(result):
    if result is None:
        return ''
    if result.accepted:
        return '<p class="qualified">Saved.</p>'
    attribute = ''
    if result.reasons:
        attribute = f' data-reason="{escape(" ".join(result.reasons))}"'
    return f'<p class="break"{attribute}>{escape(result.message)}</p>'


def _portfolio(state, result=None, status=200):
    book = state.entered
    parts = [
        f'<p>{escape(ENTERED_SENTENCE)}</p>',
        '<p>Reporting currency is NOK. Foreign currency stays in its own currency.</p>',
        f'<p><a href="{_entered_valuation_href(book)}">Value this portfolio</a></p>',
    ]
    if book.load_error:
        parts.append(f'<p class="break">{escape(book.load_error)}</p>')
    parts.append(_result_banner(result))
    if not book.load_error:
        parts.append('<h2>Accounts</h2>')
        if book.accounts:
            rows = []
            for account in book.accounts:
                rows.append(
                    '<tr>'
                    f'<td>{escape(account["institution"])}</td>'
                    f'<td>{escape(account["name"])}</td>'
                    '</tr>'
                )
            parts.append(
                '<table><thead><tr><th>Institution</th><th>Account</th>'
                '</tr></thead><tbody>'
                + ''.join(rows)
                + '</tbody></table>'
            )
        else:
            parts.append('<p>No accounts yet.</p>')
        parts.append('<h2>Instruments</h2>')
        if book.instruments:
            rows = []
            for instrument in book.instruments:
                identification = instrument['isin'] or INCOMPLETE_IDENTIFICATION
                rows.append(
                    '<tr>'
                    f'<td>{escape(instrument["display_name"])}</td>'
                    f'<td>{escape(instrument["kind"])}</td>'
                    f'<td>{escape(instrument["listing_currency"])}</td>'
                    f'<td>{escape(identification)}</td>'
                    '</tr>'
                )
            parts.append(
                '<table><thead><tr><th>Name</th><th>Kind</th>'
                '<th>Listing currency</th><th>Identification</th>'
                '</tr></thead><tbody>'
                + ''.join(rows)
                + '</tbody></table>'
            )
        else:
            parts.append('<p>No instruments yet.</p>')
        parts.append('<h2>Activities</h2>')
        if book.activities:
            rows = []
            for row in book.activities:
                label = display_activity(row['activity'])
                rows.append(
                    f'<tr data-activity="{escape(row["activity"])}">'
                    f'<td>{escape(label)}</td>'
                    f'<td>{escape(row["event_date"])}</td>'
                    f'<td>{escape(_activity_detail(row))}</td>'
                    '</tr>'
                )
            parts.append(
                '<table><thead><tr><th>Activity</th><th>Date</th>'
                '<th>Detail</th></tr></thead><tbody>'
                + ''.join(rows)
                + '</tbody></table>'
            )
        else:
            parts.append('<p>No activities yet.</p>')
        parts.append('<h2>Cash and quantities</h2>')
        snapshot = book.books()
        if snapshot is None:
            parts.append(
                '<p>No activity has been recorded, so there is no cash '
                'or quantity to show.</p>'
            )
        else:
            parts.append(
                f'<p>Cash and quantities on {escape(snapshot.on_date)}.</p>'
            )
            cash_rows = []
            for cash in snapshot.cash:
                cash_rows.append(
                    f'<tr data-currency="{escape(cash.currency)}">'
                    f'<td>{escape(book.account_label(cash.account))}</td>'
                    f'<td>{escape(cash.currency)}</td>'
                    f'<td class="figure">{_figure(cash.amount)}</td>'
                    '</tr>'
                )
            if cash_rows:
                parts.append(
                    '<table><thead><tr><th>Account</th><th>Currency</th>'
                    '<th class="figure">Amount</th></tr></thead><tbody>'
                    + ''.join(cash_rows)
                    + '</tbody></table>'
                )
            else:
                parts.append('<p>No cash remains on this date.</p>')
            position_rows = []
            for position in snapshot.positions:
                position_rows.append(
                    '<tr>'
                    f'<td>{escape(book.account_label(position.account))}</td>'
                    f'<td>{escape(book.instrument_label(position.instrument))}</td>'
                    f'<td class="figure">{_figure(position.quantity)}</td>'
                    '</tr>'
                )
            if position_rows:
                parts.append(
                    '<table><thead><tr><th>Account</th><th>Instrument</th>'
                    '<th class="figure">Quantity</th></tr></thead><tbody>'
                    + ''.join(position_rows)
                    + '</tbody></table>'
                )
            else:
                parts.append('<p>No quantity remains on this date.</p>')
        parts.append('<h2>Manual balances</h2>')
        parts.append(f'<p>{escape(SNAPSHOT_SENTENCE)}</p>')
        if book.manual_balances:
            rows = []
            for row in book.manual_balances:
                if row['holding'] == 'cash':
                    holding = 'cash'
                else:
                    holding = book.instrument_label(row['instrument'])
                rows.append(
                    '<tr>'
                    f'<td>{escape(book.account_label(row["account"]))}</td>'
                    f'<td>{escape(holding)}</td>'
                    f'<td class="figure">{escape(row["amount"])}</td>'
                    f'<td>{escape(row["currency"])}</td>'
                    f'<td>{escape(row["as_of"])}</td>'
                    '</tr>'
                )
            parts.append(
                '<table><thead><tr><th>Account</th><th>Holding</th>'
                '<th class="figure">Amount</th><th>Currency</th><th>As of</th>'
                '</tr></thead><tbody>'
                + ''.join(rows)
                + '</tbody></table>'
            )
        else:
            parts.append('<p>No manual balances yet.</p>')
    parts.append('<h2>Add an account</h2>')
    parts.append(
        '<form method="post" action="/portfolio" '
        'enctype="application/x-www-form-urlencoded">'
        '<input type="hidden" name="action" value="account">'
        + _portfolio_input('account', 'institution', 'Institution')
        + _portfolio_input('account', 'account_name', 'Account name')
        + '<button type="submit">Add account</button></form>'
    )
    parts.append('<h2>Add an instrument</h2>')
    kind_options = [('', 'Choose a kind')]
    for kind in KINDS:
        kind_options.append((kind, kind))
    parts.append(
        '<form method="post" action="/portfolio" '
        'enctype="application/x-www-form-urlencoded">'
        '<input type="hidden" name="action" value="instrument">'
        + _portfolio_input('instrument', 'display_name', 'Name')
        + _portfolio_select('instrument', 'kind', 'Kind', kind_options)
        + _portfolio_input('instrument', 'listing_currency', 'Listing currency')
        + _portfolio_input('instrument', 'isin', 'ISIN, if you have one')
        + '<p>Leave the ISIN blank when you do not have one.</p>'
        + '<button type="submit">Add instrument</button></form>'
    )
    activity_options = [('', 'Choose an activity')]
    for word in ACTIVITY_WORDS:
        activity_options.append((word, word))
    parts.append('<h2>Record an activity</h2>')
    parts.append(
        '<p>Contribution, withdrawal, and fee use an amount and a currency. '
        'Purchase and sale use an instrument, a quantity, a cash amount, a '
        'cash currency, and a fee of zero or more. Dividend uses an '
        'instrument, an amount, and a currency. Manual balance uses cash or '
        'one instrument, an amount, a currency, and the date as the as-of '
        'date.</p>'
        '<form method="post" action="/portfolio" '
        'enctype="application/x-www-form-urlencoded">'
        '<input type="hidden" name="action" value="activity">'
        + _portfolio_select('activity', 'activity', 'Activity', activity_options)
        + _portfolio_select('activity', 'account', 'Account', _account_choices(book))
        + _portfolio_select(
            'activity',
            'instrument',
            'Instrument',
            _instrument_choices(book),
        )
        + _portfolio_select(
            'activity',
            'balance_subject',
            'Manual balance holding',
            _balance_choices(book),
        )
        + _portfolio_input('activity', 'event_date', 'Date')
        + _portfolio_input('activity', 'provenance', 'Where this came from')
        + _portfolio_input('activity', 'currency', 'Currency')
        + _portfolio_input('activity', 'amount', 'Amount')
        + _portfolio_input('activity', 'quantity', 'Quantity')
        + _portfolio_input('activity', 'cash_currency', 'Cash currency')
        + _portfolio_input('activity', 'cash_amount', 'Cash amount')
        + _portfolio_input('activity', 'fee', 'Fee')
        + '<button type="submit">Save activity</button></form>'
    )
    return _page(state, 'Entered portfolio', ''.join(parts), status, footer='')


def _post_portfolio(state, form):
    book = state.entered
    action = _field(form, 'action')
    if action == 'account':
        result = book.add_account(
            _field(form, 'institution'),
            _field(form, 'account_name'),
        )
    elif action == 'instrument':
        result = book.add_instrument(
            _field(form, 'display_name'),
            _field(form, 'kind'),
            _field(form, 'listing_currency'),
            _field(form, 'isin'),
        )
    elif action == 'activity':
        activity = _field(form, 'activity')
        if activity == 'manual balance':
            result = book.add_manual_balance(
                _field(form, 'account'),
                _field(form, 'balance_subject'),
                _field(form, 'amount'),
                _field(form, 'currency'),
                _field(form, 'event_date'),
                _field(form, 'provenance'),
            )
        else:
            result = book.add_activity(
                activity,
                _field(form, 'account'),
                _field(form, 'event_date'),
                _field(form, 'provenance'),
                currency=_field(form, 'currency'),
                amount=_field(form, 'amount'),
                instrument=_field(form, 'instrument'),
                quantity=_field(form, 'quantity'),
                cash_currency=_field(form, 'cash_currency'),
                cash_amount=_field(form, 'cash_amount'),
                fee=_field(form, 'fee'),
            )
    else:
        result = book.add_activity(
            '',
            '',
            '',
            '',
        )
    status = 200 if result.accepted else 400
    return _portfolio(state, result, status)


def _entered_valuation_href(book):
    day = book.latest_activity_date()
    if not day:
        return '/portfolio/valuation'
    return '/portfolio/valuation?date=' + escape(day)


def _entered_line_amount(line):
    if not line.known or line.amount is None:
        return 'unknown'
    return _figure(line.amount)


def _allocation_incomplete_paragraph():
    return f'<p>{escape(ALLOCATION_INCOMPLETE)}</p>'


def _entered_shares_shown(report):
    """Shares need known NOK lines and a non-zero known NOK subtotal."""
    return bool(
        report.allocation_complete
        and report.known_nok_subtotal != 0
        and report.shares
    )


def _entered_valuation(state, source, result=None, status=200):
    book = state.entered
    day = _field(source, 'date')
    parts = [
        f'<p>{escape(VALUATION_SENTENCE)}</p>',
        f'<p>{escape(MISSING_PRICE_SENTENCE)}</p>',
        f'<p>{escape(SNAPSHOT_VALUE_SENTENCE)}</p>',
        '<p><a href="/portfolio">Entered portfolio</a></p>',
        '<p><a href="/portfolio/performance">Performance</a></p>',
        '<p><a href="/portfolio/price">Accept a stored price</a></p>',
        _result_banner(result),
    ]
    if book.load_error:
        parts.append(f'<p class="break">{escape(book.load_error)}</p>')
        parts.append(_allocation_incomplete_paragraph())
        parts.append(_date_form('/portfolio/valuation', day))
        return _page(state, 'Entered valuation', ''.join(parts), status, footer='')
    report = None
    if day == '':
        parts.append('<p>Enter the date.</p>')
        parts.append(_allocation_incomplete_paragraph())
    else:
        report = book.value_on(day)
        if report.error:
            status = 400
            parts.append(f'<p class="break">{escape(report.error)}</p>')
            parts.append(_allocation_incomplete_paragraph())
        else:
            parts.append(f'<p>Valuation on {escape(report.on_date)}.</p>')
            parts.append(_entered_value_table(book, report))
            parts.append(
                '<p data-nok-subtotal="'
                + _figure(report.known_nok_subtotal)
                + '">known NOK subtotal <span class="figure">'
                + _figure(report.known_nok_subtotal)
                + '</span></p>'
            )
            if report.note == CASH_SNAPSHOT_NOT_ADDED:
                parts.append(f'<p>{escape(CASH_SNAPSHOT_NOT_ADDED)}</p>')
            if _entered_shares_shown(report):
                parts.append(_entered_shares(book, report))
            else:
                parts.append(_allocation_incomplete_paragraph())
            parts.append('<h2>Historical value</h2>')
            parts.append(_entered_history(report))
    parts.append(_date_form('/portfolio/valuation', day if report is None or report.error else report.on_date))
    if not book.load_error:
        parts.append('<h2>Entered prices</h2>')
        parts.append(_entered_price_table(book, day if report is None or report.error else report.on_date))
        parts.append(_entered_price_form(book, day if report is None or report.error else report.on_date))
    return _page(state, 'Entered valuation', ''.join(parts), status, footer='')


def _entered_value_table(book, report):
    if not report.lines:
        return '<p>Nothing is recorded for this date.</p>'
    rows = []
    for line in report.lines:
        amount = _entered_line_amount(line)
        amount_attribute = ''
        if line.known and line.amount is not None:
            amount_attribute = f' data-amount="{_figure(line.amount)}"'
        freshness = ''
        freshness_attribute = ''
        if line.freshness:
            freshness = line.freshness
            freshness_attribute = f' data-freshness="{escape(line.freshness)}"'
        label = line.detail
        rows.append(
            '<tr'
            f' data-kind="{escape(line.kind)}"'
            f' data-known="{"true" if line.known else "false"}"'
            f' data-identity="{escape(line.identity)}"'
            f' data-currency="{escape(line.currency)}"'
            f'{amount_attribute}'
            f'{freshness_attribute}'
            '>'
            f'<td>{escape(book.account_label(line.account))}</td>'
            f'<td>{escape(_entered_holding_label(book, line))}</td>'
            f'<td>{escape(line.kind)}</td>'
            f'<td>{escape(line.currency)}</td>'
            f'<td class="figure">{amount}</td>'
            f'<td>{escape(freshness)}</td>'
            f'<td>{escape(label)}</td>'
            '</tr>'
        )
    return (
        '<table><thead><tr><th>Account</th><th>Holding</th><th>Kind</th>'
        '<th>Currency</th><th class="figure">Value</th><th>Freshness</th>'
        '<th>Note</th></tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )


def _entered_holding_label(book, line):
    if line.kind == 'cash' or line.identity == 'cash':
        return 'cash'
    return book.instrument_label(line.identity)


def _entered_shares(book, report):
    rows = []
    for line, share in zip(report.lines, report.shares):
        shown = _figure(share)
        rows.append(
            '<tr'
            f' data-kind="{escape(line.kind)}"'
            f' data-identity="{escape(line.identity)}"'
            f' data-share="{shown}"'
            '>'
            f'<td>{escape(_entered_holding_label(book, line))}</td>'
            f'<td>{escape(line.currency)}</td>'
            f'<td class="figure">{shown}</td>'
            '</tr>'
        )
    return (
        '<h2>Allocation</h2>'
        '<table><thead><tr><th>Holding</th><th>Currency</th>'
        '<th class="figure">Share</th></tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )


def _entered_history(report):
    rows = []
    for point in report.history:
        shown = _figure(point.known_nok_subtotal)
        rows.append(
            '<p'
            f' data-history="{escape(point.on_date)}"'
            f' data-nok-subtotal="{shown}"'
            f' data-unknown="{point.unknown_count}"'
            '>'
            f'{escape(point.on_date)} known NOK subtotal {shown}. '
            f'Unknown lines {point.unknown_count}.'
            '</p>'
        )
    return ''.join(rows)


def _entered_price_table(book, selected):
    if not book.prices:
        return '<p>No prices yet.</p>'
    rows = []
    for price in book.prices:
        freshness = ''
        if selected:
            try:
                freshness = ' '.join(price_freshness(
                    price['valuation_date'],
                    price['evidence_date'],
                    selected,
                ))
            except ValueError:
                freshness = ''
        rows.append(
            '<tr'
            f' data-valuation-date="{escape(price["valuation_date"])}"'
            f' data-instrument="{escape(price["instrument"])}"'
            + (f' data-freshness="{escape(freshness)}"' if freshness else '')
            + '>'
            f'<td>{escape(book.instrument_label(price["instrument"]))}</td>'
            f'<td class="figure">{escape(price["amount"])}</td>'
            f'<td>{escape(price["currency"])}</td>'
            f'<td>{escape(price["valuation_date"])}</td>'
            f'<td>{escape(price["evidence_date"])}</td>'
            f'<td>{escape(price["provenance"])}</td>'
            f'<td>{escape(freshness)}</td>'
            '</tr>'
        )
    return (
        '<table><thead><tr><th>Instrument</th><th class="figure">Amount</th>'
        '<th>Currency</th><th>Valuation date</th><th>Evidence date</th>'
        '<th>Where this came from</th><th>Freshness</th></tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )


def _entered_price_form(book, selected):
    hidden_date = ''
    if selected:
        hidden_date = (
            '<input type="hidden" name="date" value="'
            + escape(selected)
            + '">'
        )
    return (
        '<h2>Record a price</h2>'
        '<form method="post" action="/portfolio/valuation" '
        'enctype="application/x-www-form-urlencoded">'
        '<input type="hidden" name="action" value="price">'
        + hidden_date
        + _portfolio_select(
            'price',
            'instrument',
            'Instrument',
            _instrument_choices(book),
        )
        + _portfolio_input('price', 'amount', 'Amount')
        + _portfolio_input('price', 'currency', 'Currency')
        + _portfolio_input('price', 'valuation_date', 'Valuation date')
        + _portfolio_input('price', 'evidence_date', 'Evidence date')
        + _portfolio_input('price', 'provenance', 'Where this came from')
        + '<button type="submit">Save price</button></form>'
    )


def _performance_form(start, end):
    return (
        '<form method="get" action="/portfolio/performance">'
        '<label for="start">Start'
        f'<input id="start" name="start" value="{escape(start)}">'
        '</label>'
        '<label for="end">End'
        f'<input id="end" name="end" value="{escape(end)}">'
        '</label>'
        '<button type="submit">Show this window</button>'
        '</form>'
    )


def _labeled_figure(label, amount):
    shown = _figure(amount)
    slug = label.replace(' ', '-')
    return (
        f'<p data-{slug}="{shown}">{escape(label)} '
        f'<span class="figure">{shown}</span></p>'
    )


def _entered_performance(state, source):
    book = state.entered
    start = _field(source, 'start')
    end = _field(source, 'end')
    parts = [
        f'<p>{escape(ATTRIBUTION_SENTENCE)}</p>',
        '<p><a href="/portfolio/valuation">Entered valuation</a></p>',
    ]
    status = 200
    if book.load_error:
        parts.append(f'<p class="break">{escape(book.load_error)}</p>')
    elif start == '' or end == '':
        if start == '':
            parts.append('<p>Enter the start date.</p>')
        if end == '':
            parts.append('<p>Enter the end date.</p>')
    else:
        report = book.attribute(start, end)
        if report.start_date:
            start = report.start_date
        if report.end_date:
            end = report.end_date
        if report.error:
            status = 400
            parts.append(f'<p class="break">{escape(report.error)}</p>')
        elif report.unavailable:
            parts.append(f'<p>{escape(ATTRIBUTION_UNAVAILABLE)}</p>')
        else:
            parts.append(f'<p>{escape(FEE_SENTENCE)}</p>')
            parts.append(f'<p>{escape(DIVIDEND_SENTENCE)}</p>')
            parts.append(_labeled_figure('start value', report.start_value))
            parts.append(_labeled_figure('end value', report.end_value))
            parts.append(_labeled_figure('contributions', report.contributions))
            parts.append(_labeled_figure('withdrawals', report.withdrawals))
            parts.append(_labeled_figure('fees', report.fees))
            parts.append(_labeled_figure('dividends', report.dividends))
            parts.append(_labeled_figure('price change', report.price_change))
    parts.append(_performance_form(start, end))
    return _page(state, 'Entered performance', ''.join(parts), status, footer='')


def _post_entered_valuation(state, form):
    book = state.entered
    action = _field(form, 'action')
    if action != 'price':
        result = book.record_price('', '', '', '', '', '')
        return _entered_valuation(state, form, result, 400)
    result = book.record_price(
        _field(form, 'instrument'),
        _field(form, 'amount'),
        _field(form, 'currency'),
        _field(form, 'valuation_date'),
        _field(form, 'evidence_date'),
        _field(form, 'provenance'),
    )
    status = 200 if result.accepted else 400
    source = dict(form)
    if result.accepted and _field(form, 'date') == '':
        source = dict(form)
        source['date'] = _field(form, 'valuation_date')
    return _entered_valuation(state, source, result, status)


ACCEPT_NOT_RECOMMENDATION = 'This accept is not a recommendation.'
STORED_RATE_NOT_COPIED = 'A stored rate is not copied unless you accept it.'
NOT_A_HOLDING_PRICE = 'This observation is not a price for this holding.'
_NOT_HOLDING_SUBJECTS = frozenset({
    'USD/NOK',
    'EUR/NOK',
    'policy-rate',
    'nowa',
    'cpi-total',
})


def _listing_currency(book, identity):
    for instrument in book.instruments:
        if instrument.get('identity') == identity:
            return instrument.get('listing_currency')
    return None


def _chosen_observation(rows, observation_id):
    """One visible row with this id. A missing or repeated id is not chosen."""
    if not isinstance(observation_id, str) or observation_id == '':
        return None
    matches = [
        row for row in rows
        if row.observation_id == observation_id
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _holding_price_refusal(observation, listing_currency):
    """None when this stored row may be accepted as an entered price."""
    if not isinstance(observation, Observation):
        return NOT_A_HOLDING_PRICE
    if 'synthetic_fixture' in observation.quality:
        return NOT_A_HOLDING_PRICE
    if observation.subject in _NOT_HOLDING_SUBJECTS:
        return NOT_A_HOLDING_PRICE
    if listing_currency is None or observation.unit != listing_currency:
        return NOT_A_HOLDING_PRICE
    value = observation.value
    if not isinstance(value, Decimal) or not value.is_finite():
        return NOT_A_HOLDING_PRICE
    return None


def _accept_stored_observation(book, rows, instrument_id, observation_id):
    """Store one entered price, or refuse without writing."""
    observation = _chosen_observation(rows, observation_id)
    listing = _listing_currency(book, instrument_id)
    refusal = _holding_price_refusal(observation, listing)
    if refusal is not None:
        return EntryResult(False, refusal, (), '')
    return book.record_price(
        instrument_id,
        observation.value,
        observation.unit,
        observation.observation_time.isoformat(),
        observation.retrieval_time.isoformat(),
        observation.observation_id,
    )


def _observation_amount(value):
    if value is None:
        return 'missing'
    if isinstance(value, Decimal):
        return format(value, 'f')
    return str(value)


def _stored_observation_table(rows):
    if not rows:
        return '<p>No stored observations.</p>'
    body = []
    for observation in rows:
        quality = ', '.join(observation.quality)
        body.append(
            '<tr'
            f' data-observation="{escape(observation.observation_id)}"'
            f' data-subject="{escape(observation.subject)}"'
            f' data-unit="{escape(observation.unit)}"'
            '>'
            f'<td>{escape(observation.observation_id)}</td>'
            f'<td>{escape(observation.subject)}</td>'
            f'<td>{escape(observation.unit)}</td>'
            f'<td class="figure">{escape(_observation_amount(observation.value))}</td>'
            f'<td>{escape(observation.observation_time.isoformat())}</td>'
            f'<td>{escape(observation.retrieval_time.isoformat())}</td>'
            f'<td>{escape(quality)}</td>'
            '</tr>'
        )
    return (
        '<table><thead><tr><th>Observation</th><th>Subject</th><th>Unit</th>'
        '<th class="figure">Value</th><th>Observed</th><th>Retrieved</th>'
        '<th>Quality</th></tr></thead><tbody>'
        + ''.join(body)
        + '</tbody></table>'
    )


def _observation_choices(rows):
    choices = [('', 'Choose an observation')]
    for observation in rows:
        label = (
            f'{observation.observation_id} {observation.subject} '
            f'{observation.unit}'
        )
        choices.append((observation.observation_id, label))
    return choices


def _accept_price_form(book, rows):
    return (
        '<h2>Accept one observation</h2>'
        '<form method="post" action="/portfolio/price" '
        'enctype="application/x-www-form-urlencoded">'
        + _portfolio_select(
            'accept',
            'instrument',
            'Instrument',
            _instrument_choices(book),
        )
        + _portfolio_select(
            'accept',
            'observation_id',
            'Observation',
            _observation_choices(rows),
        )
        + '<button type="submit">Accept observation</button></form>'
    )


def _entered_price_accept(state, result=None, status=200):
    book = state.entered
    parts = [
        f'<p>{escape(ACCEPT_NOT_RECOMMENDATION)}</p>',
        f'<p>{escape(STORED_RATE_NOT_COPIED)}</p>',
        '<p><a href="/portfolio/valuation">Entered valuation</a></p>',
        _result_banner(result),
    ]
    try:
        store, _cached = open_recorded_store(state)
        rows = visible_observations(store)
    except ValueError as exc:
        parts.append(f'<p class="break">{escape(str(exc))}</p>')
        rows = ()
    parts.append('<h2>Stored observations</h2>')
    parts.append(_stored_observation_table(rows))
    parts.append(_accept_price_form(book, rows))
    return _page(state, 'Accept a stored price', ''.join(parts), status, footer='')


def _post_entered_price(state, form):
    try:
        store, _cached = open_recorded_store(state)
        rows = visible_observations(store)
    except ValueError as exc:
        result = EntryResult(False, str(exc), (), '')
        return _entered_price_accept(state, result, 400)
    result = _accept_stored_observation(
        state.entered,
        rows,
        _field(form, 'instrument'),
        _field(form, 'observation_id'),
    )
    status = 200 if result.accepted else 400
    return _entered_price_accept(state, result, status)


def dispatch(state, method, path, form):
    verb = str(method or '').upper()
    parsed = urlsplit(path or '/')
    route = parsed.path or '/'
    if route != '/':
        route = route.rstrip('/') or '/'
    query = parse_qs(parsed.query, keep_blank_values=True)
    form = {} if form is None else form
    if route.startswith('/static/desk'):
        if verb != 'GET':
            return Response(405, 'text/plain; charset=utf-8', 'That action is not available here.')
        return _static_desk(state, route)
    if verb == 'GET' and route == '/':
        return _desk(state, query)
    if verb == 'GET' and route == '/ledger':
        return _home(state)
    if verb == 'GET' and route == '/portfolio':
        return _portfolio(state)
    if verb == 'POST' and route == '/portfolio':
        return _post_portfolio(state, form)
    if verb == 'GET' and route == '/portfolio/valuation':
        return _entered_valuation(state, query)
    if verb == 'POST' and route == '/portfolio/valuation':
        return _post_entered_valuation(state, form)
    if verb == 'GET' and route == '/portfolio/price':
        return _entered_price_accept(state)
    if verb == 'POST' and route == '/portfolio/price':
        return _post_entered_price(state, form)
    if verb == 'GET' and route == '/portfolio/performance':
        return _entered_performance(state, query)
    if verb == 'GET' and route == '/api/desk':
        return _api_desk(state, query)
    if verb == 'GET' and route == '/evidence':
        return _evidence(state, query)
    if verb == 'POST' and route == '/evidence/refresh':
        return _post_evidence_refresh(state, form)
    if verb == 'GET' and route == '/conversation':
        return _conversation(state)
    if verb == 'POST' and route == '/conversation':
        return _post_conversation(state, form)
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
        return _desk(state, {})
    known = {
        '/',
        '/ledger',
        '/portfolio',
        '/portfolio/valuation',
        '/portfolio/price',
        '/portfolio/performance',
        '/api/desk',
        '/conversation',
        '/transactions',
        '/transactions/new',
        '/history',
        '/valuation',
        '/reconcile',
        '/chart',
        '/evidence',
        '/evidence/refresh',
        '/reset',
    }
    if route in known:
        return _page(state, 'Method not allowed', '<p>That action is not available here.</p>', 405)
    return _page(state, 'Missing page', '<p>That page is not in this ledger.</p>', 404)
