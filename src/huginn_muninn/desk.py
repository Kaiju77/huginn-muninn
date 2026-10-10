"""Night desk for the synthetic ledger.

The page is server-rendered from Ledger and the allocation module.
JavaScript on the conversation page may draw measured microphone levels.
It does not recognize speech, synthesize speech, or call a model.
"""

from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from html import escape
import re

from src.huginn_muninn.allocation import (
    ARITHMETIC_SENTENCE,
    compare,
)
from src.huginn_muninn.evidence import (
    MAX_AGE_DAYS,
    assess,
    freshness_flags,
    open_evidence,
)


INTELLIGENCE = (
    'The recorded fixture is not a competing interpretation. No interpretation is offered.',
    'Confidence is not assessed.',
    'Risk is not assessed. No risk model is loaded.',
    'No forecast is computed.',
    'Loaded evidence is a recorded synthetic fixture. It does not support a recommendation.',
)

_SPEECH = 'No audio input. Speech recognition is not implemented.'

_CSS = """
body {
  margin: 0;
  background: #14181f;
  color: #e7e2d6;
  font-family: "Segoe UI", Candara, sans-serif;
  font-size: 1rem;
  line-height: 1.45;
  text-align: left;
}
main {
  width: min(70rem, calc(100% - 2rem));
  margin: 0 auto;
  padding: 1.25rem 0 3rem;
}
h1, .total {
  font-family: "Palatino Linotype", Palatino, Georgia, serif;
  font-weight: normal;
  text-align: left;
}
h1 {
  font-size: 1.7rem;
  line-height: 1.15;
  margin: 0.2rem 0 0.8rem;
}
h2 {
  font-family: "Segoe UI", Candara, sans-serif;
  font-weight: 600;
  font-size: 1.05rem;
  margin: 0.2rem 0 0.45rem;
}
p { max-width: 40rem; }
.total {
  font-size: 2.6rem;
  line-height: 1.05;
  margin: 0.2rem 0;
  font-variant-numeric: tabular-nums;
}
.qualified { color: #d7b58a; }
.break { color: #d07a6a; }
.dim { color: #8d97a3; }
nav a {
  color: #e7e2d6;
  margin: 0 1rem 0.4rem 0;
  display: inline-block;
}
a:focus,
button:focus,
input:focus,
textarea:focus,
select:focus {
  outline: 2px solid #d7b58a;
  outline-offset: 3px;
}
.split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  column-gap: 2rem;
  align-items: start;
}
section {
  border-top: 1px solid #2a3140;
  margin-top: 1.2rem;
  padding-top: 0.7rem;
}
.table-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.3rem 0 0.9rem;
}
th, td {
  padding: 0.35rem 0.7rem 0.35rem 0;
  border-bottom: 1px solid #2a3140;
  text-align: left;
  vertical-align: baseline;
}
.figure {
  font-family: "Cascadia Mono", Consolas, monospace;
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}
th.figure { text-align: right; }
label { display: block; margin-top: 0.8rem; }
input, textarea, button, select {
  font: inherit;
  color: #e7e2d6;
  background: #14181f;
  border: 1px solid #2a3140;
}
input, textarea, select {
  width: 100%;
  max-width: 28rem;
  padding: 0.35rem 0.45rem;
}
textarea { min-height: 6rem; }
button {
  margin-top: 0.8rem;
  padding: 0.4rem 0.75rem;
  border-color: #d7b58a;
}
.waveform {
  display: flex;
  align-items: flex-end;
  gap: 0.35rem;
  height: 4.5rem;
  margin: 0.8rem 0 0.4rem;
}
.waveform i {
  display: block;
  width: 0.45rem;
  height: 18%;
  background: #8d97a3;
}
svg { width: 100%; height: auto; display: block; }
.question { margin-bottom: 0.2rem; }
.reply { margin-top: 0; }
.note { margin-top: 2rem; }
@media (max-width: 720px) {
  main { width: calc(100% - 1.25rem); }
  .split { display: block; }
  .total { font-size: 2rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
"""


def _context():
    return Context(prec=28, rounding=ROUND_HALF_EVEN)


def _money(amount):
    if not isinstance(amount, Decimal):
        return None
    return format(amount, 'f')


def _points(difference):
    if difference is None:
        return None
    with localcontext(_context()):
        return difference * Decimal('100')


def _listings(document):
    found = {}
    for row in document.get('instruments', ()):
        identity = row.get('identity')
        currency = row.get('listing_currency')
        if isinstance(identity, str) and isinstance(currency, str):
            found[identity] = currency
    return found


def _targets(document):
    raw = document.get('targets')
    if not isinstance(raw, dict):
        return {}
    parsed = {}
    for key, value in raw.items():
        if not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, str):
            return {}
        try:
            parsed[key] = Decimal(value)
        except InvalidOperation:
            return {}
    return parsed


def _allocation_result(state, on_date):
    valuation = state.ledger.value(on_date)
    return valuation, compare(
        valuation,
        _targets(state.document),
        _listings(state.document),
    )


def _citations(state, valuation):
    price_ids = []
    rate_ids = []
    for line in valuation.lines:
        if line.price_id and line.price_id not in price_ids:
            price_ids.append(line.price_id)
        if line.rate_id and line.rate_id not in rate_ids:
            rate_ids.append(line.rate_id)
    prices = {}
    for row, posting in state.price_postings:
        if posting.accepted:
            prices[row.get('observation_id')] = row
    rates = {}
    for row, posting in state.rate_postings:
        if posting.accepted:
            rates[row.get('rate_id')] = row
    citations = []
    for identity in price_ids:
        row = prices.get(identity)
        if row is None:
            continue
        citations.append({
            'kind': 'price',
            'id': identity,
            'provenance': row.get('provenance') or '',
            'instrument': row.get('instrument') or '',
            'currency': row.get('price_currency') or '',
            'observed': row.get('valuation_date') or '',
            'evidence_date': row.get('evidence_date') or '',
        })
    for identity in rate_ids:
        row = rates.get(identity)
        if row is None:
            continue
        base = row.get('base') or ''
        quote = row.get('quote') or ''
        citations.append({
            'kind': 'rate',
            'id': identity,
            'provenance': row.get('provenance') or '',
            'pair': f'{base}/{quote}',
            'observed': row.get('rate_date') or '',
            'evidence_date': row.get('evidence_date') or '',
        })
    return citations


def _residual_statement(performance):
    identity = (
        'This residual is an accounting identity. '
        'It is not a return, not an annualized figure, and not a forecast.'
    )
    if performance.residual is None and 'incomplete' in performance.residual_reasons:
        return (
            'The residual is unknown because the valuation is incomplete. '
            + identity
        )
    if performance.residual is None:
        return 'The residual is unknown. ' + identity
    return identity


def _allocation_payload(result):
    rows = []
    if result.status == 'complete':
        for row in result.rows:
            rows.append({
                'key': row.key,
                'kind': row.kind,
                'current_amount': _money(row.current_amount),
                'current_weight': _money(row.current_weight),
                'target_weight': _money(row.target_weight),
                'weight_difference': _money(row.weight_difference),
                'percentage_point_gap': _money(_points(row.weight_difference)),
                'illustrative_amount': _money(row.illustrative_amount),
                'recommendation': None,
            })
    return {
        'status': result.status,
        'sentence': result.sentence,
        'rows': rows,
        'valuation_reasons': [
            {'identity': item.identity, 'reasons': list(item.reasons)}
            for item in result.valuation_reasons
        ],
    }


def _performance_payload(state, performance):
    positions = []
    for row in performance.positions:
        positions.append({
            'account': row.account,
            'instrument': row.instrument,
            'display_name': state.display_name(row.instrument),
            'quantity': _money(row.quantity),
            'cost': _money(row.cost),
            'cost_currency': row.cost_currency,
            'reasons': list(row.reasons),
        })
    realized = []
    for row in performance.realized:
        realized.append({
            'event_id': row.event_id,
            'instrument': row.instrument,
            'display_name': state.display_name(row.instrument),
            'quantity': _money(row.quantity),
            'cash_currency': row.cash_currency,
            'proceeds': _money(row.proceeds),
            'removed_cost': _money(row.removed_cost),
            'gain': _money(row.gain),
            'reasons': list(row.reasons),
        })
    unrealized = []
    for row in performance.unrealized:
        unrealized.append({
            'instrument': row.instrument,
            'display_name': state.display_name(row.instrument),
            'reporting_amount': _money(row.reporting_amount),
            'cost': _money(row.cost),
            'cost_currency': row.cost_currency,
            'gain': _money(row.gain),
            'reasons': list(row.reasons),
            'rate_id': row.rate_id,
        })
    dividends = []
    for row in performance.dividends:
        dividends.append({
            'event_id': row.event_id,
            'instrument': row.instrument,
            'display_name': state.display_name(row.instrument),
            'currency': row.currency,
            'amount': _money(row.amount),
            'included': row.included,
            'reasons': list(row.reasons),
        })
    return {
        'positions': positions,
        'realized': realized,
        'unrealized': unrealized,
        'dividends': dividends,
        'dividend_income': _money(performance.dividend_income),
        'residual': _money(performance.residual),
        'residual_reasons': list(performance.residual_reasons),
        'residual_statement': _residual_statement(performance),
    }


def build_payload(state, on_date):
    """JSON-ready desk reading. Decimal values are already strings."""
    valuation, result = _allocation_result(state, on_date)
    performance = state.ledger.performance(on_date)
    listings = _listings(state.document)
    cash = []
    holdings = []
    for line in valuation.lines:
        reporting = _money(line.reporting_amount)
        if line.kind == 'cash':
            cash.append({
                'account': line.account,
                'currency': line.identity,
                'amount': _money(line.quantity_or_amount),
                'reporting_amount': reporting,
                'reasons': list(line.reasons),
            })
            continue
        if line.kind != 'position':
            continue
        holdings.append({
            'account': line.account,
            'identity': line.identity,
            'display_name': state.display_name(line.identity),
            'listing_currency': listings.get(line.identity, ''),
            'quantity': _money(line.quantity_or_amount),
            'reporting_amount': reporting,
            'price_id': line.price_id,
            'rate_id': line.rate_id,
            'reasons': list(line.reasons),
        })
    history = []
    for day in state.observation_dates():
        point = state.ledger.value(day)
        history.append({
            'date': day,
            'known_subtotal': _money(point.known_subtotal),
            'complete': point.complete,
        })
    return {
        'date': on_date,
        'reporting_currency': state.ledger.reporting_currency,
        'known_subtotal': _money(valuation.known_subtotal),
        'complete': valuation.complete,
        'cash': cash,
        'holdings': holdings,
        'allocation': _allocation_payload(result),
        'exposure': {
            'label': result.exposure_label,
            'rows': [
                {
                    'listing_currency': row.listing_currency,
                    'reporting_amount': _money(row.reporting_amount),
                }
                for row in result.exposure
            ],
        },
        'performance': _performance_payload(state, performance),
        'citations': _citations(state, valuation),
        'intelligence': list(INTELLIGENCE),
        'history': history,
    }


def _page(body):
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Huginn &amp; Muninn</title>\n'
        '<style>\n'
        + _CSS
        + '</style>\n'
        '</head>\n'
        '<body>\n'
        + body
        + '\n</body>\n</html>\n'
    )


def _nav(state):
    latest = state.latest_date()
    history = '/history'
    valuation = '/valuation'
    if latest:
        history = '/history?date=' + escape(latest)
        valuation = '/valuation?date=' + escape(latest)
    links = (
        ('/', 'Desk'),
        ('/ledger', 'Ledger'),
        ('/transactions', 'Transactions'),
        ('/transactions/new', 'Record a transaction'),
        (history, 'History'),
        (valuation, 'Valuation'),
        ('/reconcile', 'Reconciliation'),
        ('/chart', 'Chart'),
        ('/conversation', 'Conversation'),
        ('/evidence', 'Evidence'),
    )
    return '<nav>' + ''.join(
        f'<a href="{href}">{escape(label)}</a>' for href, label in links
    ) + '</nav>'


def _shell(state, inner):
    return _page(
        '<main>\n'
        + _nav(state)
        + '<h1>Huginn &amp; Muninn</h1>\n'
        + inner
        + '<p class="note">These figures are synthetic. This page is not a recommendation.</p>\n'
        + '</main>'
    )


def _cell(text, figure=False):
    css = ' class="figure"' if figure else ''
    return f'<td{css}>{text}</td>'


def _text(value):
    if value is None:
        return ''
    return escape(str(value))


def _reason_text(reasons):
    if not reasons:
        return ''
    return escape(', '.join(reasons))


def _cash_table(payload):
    rows = []
    for row in payload['cash']:
        amount_class = 'figure qualified' if row['reporting_amount'] is not None else 'figure'
        rows.append(
            '<tr>'
            f'<td>Cash {escape(row["currency"])}</td>'
            + _cell(_text(row['amount']), True)
            + f'<td class="{amount_class}">{_text(row["reporting_amount"])}</td>'
            f'<td>{_reason_text(row["reasons"])}</td>'
            '</tr>'
        )
    if not rows:
        return '<p class="dim">No cash row is open.</p>'
    return (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Cash</th><th class="figure">Amount</th>'
        '<th class="figure">Reporting amount</th><th>Reasons</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table></div>'
    )


def _holding_table(payload):
    rows = []
    for row in payload['holdings']:
        amount_class = 'figure qualified' if row['reporting_amount'] is not None else 'figure'
        rows.append(
            '<tr'
            f' data-identity="{escape(row["identity"])}"'
            f' data-reporting="{_text(row["reporting_amount"])}"'
            '>'
            f'<td>{escape(row["display_name"])}</td>'
            f'<td>{escape(row["listing_currency"])}</td>'
            + _cell(_text(row['quantity']), True)
            + f'<td class="{amount_class}">{_text(row["reporting_amount"])}</td>'
            f'<td>{_reason_text(row["reasons"])}</td>'
            '</tr>'
        )
    if not rows:
        return '<p class="dim">No holding is open.</p>'
    return (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Holding</th><th>Listing currency</th>'
        '<th class="figure">Quantity</th>'
        '<th class="figure">Reporting amount</th><th>Reasons</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table></div>'
    )


def _allocation_table(payload):
    allocation = payload['allocation']
    sentence = f'<p>{escape(allocation["sentence"])}</p>'
    if allocation['status'] != 'complete':
        reason_bits = []
        for item in allocation['valuation_reasons']:
            reason_bits.append(
                escape(item['identity']) + ' ' + _reason_text(item['reasons'])
            )
        detail = ''
        if reason_bits:
            detail = '<p>Valuation reasons: ' + ', '.join(reason_bits) + '.</p>'
        return (
            f'<p>The allocation status is {escape(allocation["status"])}. '
            'Illustrative amounts are absent.</p>'
            + detail
            + sentence
        )
    rows = []
    for row in allocation['rows']:
        rows.append(
            '<tr'
            f' data-key="{escape(row["key"])}"'
            f' data-kind="{escape(row["kind"])}"'
            f' data-illustrative="{_text(row["illustrative_amount"])}"'
            '>'
            f'<td>{escape(row["key"])}</td>'
            f'<td>{escape(row["kind"])}</td>'
            + _cell(_text(row['current_amount']), True)
            + _cell(_text(row['current_weight']), True)
            + _cell(_text(row['target_weight']), True)
            + _cell(_text(row['percentage_point_gap']), True)
            + _cell(_text(row['illustrative_amount']), True)
            + '<td>None</td>'
            '</tr>'
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Key</th><th>Kind</th>'
        '<th class="figure">Current amount</th>'
        '<th class="figure">Current weight</th>'
        '<th class="figure">Target weight</th>'
        '<th class="figure">Gap in percentage points</th>'
        '<th class="figure">Illustrative amount</th>'
        '<th>Recommendation</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table></div>'
        + sentence
    )


def _exposure_table(payload):
    exposure = payload['exposure']
    rows = []
    for row in exposure['rows']:
        rows.append(
            '<tr>'
            f'<td>{escape(row["listing_currency"])}</td>'
            + _cell(_text(row['reporting_amount']), True)
            + '</tr>'
        )
    body = ''
    if rows:
        body = (
            '<div class="table-wrap"><table><thead><tr>'
            '<th>Listing currency</th>'
            '<th class="figure">Reporting amount</th>'
            '</tr></thead><tbody>'
            + ''.join(rows)
            + '</tbody></table></div>'
        )
    else:
        body = '<p class="dim">No qualified line has a listing currency.</p>'
    return body


def _performance_section(payload):
    performance = payload['performance']
    blocks = ['<h2>Performance</h2>']
    cost_rows = []
    for row in performance['positions']:
        cost = _text(row['cost'])
        if row['cost_currency']:
            cost = f'{cost} {escape(row["cost_currency"])}'
        cost_rows.append(
            '<tr>'
            f'<td>{escape(row["display_name"])}</td>'
            + _cell(_text(row['quantity']), True)
            + f'<td class="figure">{cost}</td>'
            f'<td>{_reason_text(row["reasons"])}</td>'
            '</tr>'
        )
    if cost_rows:
        blocks.append(
            '<div class="table-wrap"><table><thead><tr>'
            '<th>Position</th><th class="figure">Quantity</th>'
            '<th class="figure">Average cost</th><th>Reasons</th>'
            '</tr></thead><tbody>'
            + ''.join(cost_rows)
            + '</tbody></table></div>'
        )
    gain_rows = []
    for row in performance['realized']:
        gain_rows.append(
            '<tr>'
            f'<td>Realized {escape(row["display_name"])}</td>'
            f'<td class="figure">{_text(row["gain"])}</td>'
            f'<td>{_reason_text(row["reasons"])}</td>'
            '</tr>'
        )
    for row in performance['unrealized']:
        gain_class = 'figure qualified' if row['gain'] is not None else 'figure'
        shown = _text(row['gain']) if row['gain'] is not None else 'unknown'
        gain_rows.append(
            '<tr>'
            f'<td>Unrealized {escape(row["display_name"])}</td>'
            f'<td class="{gain_class}">{shown}</td>'
            f'<td>{_reason_text(row["reasons"])}</td>'
            '</tr>'
        )
    if gain_rows:
        blocks.append(
            '<div class="table-wrap"><table><thead><tr>'
            '<th>Component</th><th class="figure">Amount</th><th>Reasons</th>'
            '</tr></thead><tbody>'
            + ''.join(gain_rows)
            + '</tbody></table></div>'
        )
    blocks.append(
        '<p>Dividend income in the reporting currency '
        f'<span class="figure qualified">{_text(performance["dividend_income"])}</span>.</p>'
    )
    excluded = [
        row for row in performance['dividends'] if not row['included']
    ]
    if excluded:
        bits = []
        for row in excluded:
            bits.append(
                f'{escape(row["display_name"])} {_text(row["amount"])} '
                f'{escape(row["currency"])} {_reason_text(row["reasons"])}'
            )
        blocks.append(
            '<p>Dividends left out of that income sum: ' + ', '.join(bits) + '.</p>'
        )
    residual = performance['residual']
    if residual is None:
        blocks.append(f'<p class="break">{escape(performance["residual_statement"])}</p>')
    else:
        blocks.append(
            '<p>Residual <span class="figure qualified">'
            f'{_text(residual)}</span>. {escape(performance["residual_statement"])}</p>'
        )
    return ''.join(blocks)


def _citation_sections(payload):
    citations = payload['citations']
    if not citations:
        empty = '<p class="dim">No price or rate is cited by this valuation.</p>'
        return (
            '<section><h2>Provenance</h2>' + empty + '</section>'
            '<section><h2>Evidence</h2>' + empty + '</section>'
        )
    provenance_rows = []
    evidence_rows = []
    for item in citations:
        subject = item.get('instrument') or item.get('pair') or ''
        provenance_rows.append(
            '<tr>'
            f'<td>{escape(item["kind"])}</td>'
            f'<td>{escape(item["id"])}</td>'
            f'<td>{escape(item["provenance"])}</td>'
            '</tr>'
        )
        evidence_rows.append(
            '<li>'
            f'{escape(item["kind"])} {escape(item["id"])} '
            f'{escape(subject)} observed {escape(item["observed"])} '
            f'evidence {escape(item["evidence_date"])} '
            f'provenance {escape(item["provenance"])}'
            '</li>'
        )
    provenance = (
        '<section><h2>Provenance</h2>'
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Kind</th><th>Id</th><th>Provenance</th>'
        '</tr></thead><tbody>'
        + ''.join(provenance_rows)
        + '</tbody></table></div></section>'
    )
    evidence = (
        '<section><h2>Evidence</h2><ul>'
        + ''.join(evidence_rows)
        + '</ul></section>'
    )
    return provenance + evidence


def _chart(history):
    opening = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 720 280" role="img">'
        '<title>Known subtotal</title>'
        '<line x1="40" y1="220" x2="680" y2="220" stroke="#2a3140" stroke-width="1"></line>'
    )
    if not history:
        return opening + '</svg>'
    amounts = [Decimal(point['known_subtotal']) for point in history]
    low = min(amounts)
    high = max(amounts)
    span = high - low
    if span == 0:
        span = Decimal(1)
    slot = Decimal(640) / Decimal(len(history))
    parts = [opening]
    for index, point in enumerate(history):
        amount = amounts[index]
        ratio = (amount - low) / span
        x = Decimal(40) + (Decimal(index) + Decimal('0.5')) * slot
        y = Decimal(220) - (ratio * Decimal(160))
        complete = 'true' if point['complete'] else 'false'
        state_word = 'complete' if point['complete'] else 'incomplete'
        parts.append(
            '<g'
            f' data-date="{escape(point["date"])}"'
            f' data-subtotal="{escape(point["known_subtotal"])}"'
            f' data-complete="{complete}"'
            '>'
            f'<title>{escape(point["date"])} {escape(point["known_subtotal"])} '
            f'{state_word}</title>'
        )
        if point['complete']:
            parts.append(
                f'<circle cx="{format(x, "f")}" cy="{format(y, "f")}" r="5" fill="#d7b58a"></circle>'
            )
        else:
            parts.append(
                '<rect'
                f' x="{format(x - Decimal(5), "f")}"'
                f' y="{format(y - Decimal(5), "f")}"'
                ' width="10" height="10" fill="#d07a6a"></rect>'
            )
        parts.append('</g>')
    parts.append('</svg>')
    return ''.join(parts)


def _history_table(history):
    rows = []
    for point in history:
        status = 'complete' if point['complete'] else 'incomplete'
        css = 'figure qualified' if point['complete'] else 'figure break'
        rows.append(
            '<tr>'
            f'<td>{escape(point["date"])}</td>'
            f'<td class="{css}">{escape(point["known_subtotal"])}</td>'
            f'<td>{status}</td>'
            '</tr>'
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Date</th><th class="figure">Known subtotal</th><th>Status</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table></div>'
    )


def _intelligence(payload):
    paragraphs = ''.join(f'<p>{escape(line)}</p>' for line in payload['intelligence'])
    return '<section><h2>Intelligence</h2>' + paragraphs + '</section>'


def render_desk(state, on_date):
    payload = build_payload(state, on_date)
    flag = 'complete' if payload['complete'] else 'incomplete'
    total_class = 'total qualified' if payload['complete'] else 'total break'
    status = (
        f'<p class="{total_class}">{escape(payload["known_subtotal"])}</p>'
        '<p>Known subtotal in '
        f'{escape(payload["reporting_currency"])}. '
        f'The valuation is {flag}. Books on {escape(payload["date"])}.</p>'
    )
    books = (
        '<div class="split">'
        '<section><h2>Cash</h2>' + _cash_table(payload) + '</section>'
        '<section><h2>Holdings</h2>' + _holding_table(payload) + '</section>'
        '</div>'
    )
    allocation = (
        '<section><h2>Allocation</h2>'
        + _allocation_table(payload)
        + '</section>'
    )
    exposure = (
        '<section><h2>'
        + escape(payload['exposure']['label'])
        + '</h2>'
        + _exposure_table(payload)
        + '</section>'
    )
    chart = (
        '<section><h2>Known subtotal</h2>'
        '<figure>'
        + _chart(payload['history'])
        + '<figcaption>Stored dates only. Incomplete dates use the break color. '
        'Dates between stored observations are not added.</figcaption>'
        '</figure>'
        + _history_table(payload['history'])
        + '</section>'
    )
    controls = (
        '<section><h2>Date</h2>'
        '<form method="get" action="/">'
        '<label for="date">Date'
        f'<input id="date" name="date" value="{escape(on_date)}">'
        '</label>'
        '<button type="submit">Show this date</button>'
        '</form>'
        '<form method="post" action="/reset">'
        '<button type="submit">Reload the fixture</button>'
        '</form></section>'
    )
    inner = (
        status
        + books
        + allocation
        + exposure
        + '<section>'
        + _performance_section(payload)
        + '</section>'
        + _citation_sections(payload)
        + _intelligence(payload)
        + chart
        + controls
    )
    return _shell(state, inner)


def _evidence_amount(value):
    if value is None:
        return 'missing'
    return format(value, 'f')


def _source_limitation(source):
    parts = []
    for key in ('description', 'reason', 'blocked_reason', 'license_status', 'status'):
        value = source.get(key)
        if isinstance(value, str) and value.strip() != '':
            parts.append(value)
    references = source.get('references') or ()
    for reference in references:
        if isinstance(reference, str) and reference.strip() != '':
            parts.append(reference)
    return ' '.join(parts)


def _supplied_rate_match(state, observation):
    if observation.value is None or observation.subject != 'USD/NOK':
        return None
    observed = observation.observation_time.isoformat()
    for row, posting in state.rate_postings:
        if not posting.accepted:
            continue
        if row.get('base') != 'USD' or row.get('quote') != 'NOK':
            continue
        if row.get('rate_date') != observed:
            continue
        rate_text = row.get('rate')
        if not isinstance(rate_text, str):
            continue
        try:
            rate = Decimal(rate_text)
        except InvalidOperation:
            continue
        if rate == observation.value:
            return rate
    return None


def render_evidence(state, on_date):
    """Server-rendered registry and recorded fixture. Ledger.value is not called."""
    parsed = date.fromisoformat(on_date)
    store = open_evidence(state.fixture_path.parent.parent)
    assessment = assess(store, parsed, MAX_AGE_DAYS)
    source_rows = []
    for source in store.sources():
        fetch = 'live_fetch false' if source.get('live_fetch') is False else 'live_fetch true'
        cadence = source.get('cadence') or ''
        source_rows.append(
            '<tr>'
            f'<td>{escape(str(source.get("source_id", "")))}</td>'
            f'<td>{escape(str(source.get("publisher", "")))}</td>'
            f'<td>{escape(str(source.get("category", "")))}</td>'
            f'<td>{escape(str(cadence))}</td>'
            f'<td>{escape(fetch)}</td>'
            f'<td>{escape(_source_limitation(source))}</td>'
            '</tr>'
        )
    observation_rows = []
    match_notes = []
    for observation in store.observations():
        flags = freshness_flags(observation, parsed, MAX_AGE_DAYS)
        shown = ' '.join(flags)
        observation_rows.append(
            '<tr'
            f' data-observation="{escape(observation.observation_id)}"'
            f' data-freshness="{escape(shown)}"'
            '>'
            f'<td>{escape(observation.observation_id)}</td>'
            f'<td>{escape(observation.source_id)}</td>'
            f'<td>{escape(observation.subject)}</td>'
            f'<td>{escape(observation.unit)}</td>'
            f'<td class="figure">{escape(_evidence_amount(observation.value))}</td>'
            f'<td>{escape(observation.observation_time.isoformat())}</td>'
            f'<td>{escape(observation.retrieval_time.isoformat())}</td>'
            f'<td>{escape(shown)}</td>'
            f'<td>{escape(observation.provenance)}</td>'
            f'<td>{escape(", ".join(observation.quality))}</td>'
            '</tr>'
        )
        matched = _supplied_rate_match(state, observation)
        if matched is not None:
            shown_rate = format(matched, 'f')
            match_notes.append(
                f'<p>The number matches the ledger\'s supplied {escape(shown_rate)} rate. '
                'The match is not a live source confirmation.</p>'
            )
    conflict_notes = []
    for conflict in store.conflicts():
        visible = ', '.join(
            'missing' if value is None else format(value, 'f')
            for value in conflict.values
        )
        conflict_notes.append(
            f'<p>Conflict on {escape(conflict.observation_id)}. '
            f'Both amounts stay visible: {escape(visible)}. '
            'Neither amount was copied into the ledger.</p>'
        )
    if not conflict_notes:
        conflict_notes.append('<p>No conflicting observation is stored.</p>')
    limitations = ', '.join(assessment.limitations)
    inner = (
        '<section><h2>Evidence</h2>'
        '<p>The desk is in research mode. No source is connected. '
        'This page is not a recommendation.</p>'
        f'<p>Freshness against {escape(on_date)}. '
        f'The maximum age is {MAX_AGE_DAYS} days. '
        'The page does not read the wall clock.</p>'
        f'<p>Limitations: {escape(limitations)}.</p>'
        '<p>Loaded evidence is a recorded synthetic fixture. '
        'It does not support a recommendation.</p>'
        '</section>'
        '<section><h2>Sources</h2>'
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Source</th><th>Publisher</th><th>Category</th><th>Cadence</th>'
        '<th>Live fetch</th><th>Limitation</th>'
        '</tr></thead><tbody>'
        + ''.join(source_rows)
        + '</tbody></table></div></section>'
        '<section><h2>Recorded observations</h2>'
        '<div class="table-wrap"><table><thead><tr>'
        '<th>Observation</th><th>Source</th><th>Subject</th><th>Unit</th>'
        '<th class="figure">Value</th><th>Observed</th><th>Retrieved</th>'
        '<th>Freshness</th><th>Provenance</th><th>Quality</th>'
        '</tr></thead><tbody>'
        + ''.join(observation_rows)
        + '</tbody></table></div>'
        + ''.join(match_notes)
        + ''.join(conflict_notes)
        + '</section>'
        '<section><h2>Date</h2>'
        '<form method="get" action="/evidence">'
        '<label for="date">Date'
        f'<input id="date" name="date" value="{escape(on_date)}">'
        '</label>'
        '<button type="submit">Show this date</button>'
        '</form></section>'
    )
    return _shell(state, inner)


def render_message(state, message):
    return _shell(state, f'<p class="break">{escape(message)}</p>')


def _advice_seeking(folded):
    if 'recommend' in folded or 'should i' in folded:
        return True
    if re.search(r'\bbuy\b', folded) or re.search(r'\bsell\b', folded):
        return True
    return False


def answer(state, text):
    """Deterministic reply. This does not call a model."""
    folded = ' '.join(str(text).casefold().split())
    day = state.latest_date()
    if _advice_seeking(folded):
        return _advice_reply(state, day)
    if 'value' in folded or 'total' in folded:
        return _value_reply(state, day)
    if 'allocation' in folded or 'rebalance' in folded:
        return _allocation_reply(state, day)
    return (
        'I can explain the loaded books, the valuation, and the arithmetic gaps. '
        'That question was not one of those.'
    )


def _advice_reply(state, day):
    lead = 'This desk does not recommend a transaction.'
    if not day:
        return lead
    _valuation, result = _allocation_result(state, day)
    if result.status == 'complete':
        return lead + ' ' + result.sentence
    return lead


def _value_reply(state, day):
    if not day:
        return 'There is no book date in the loaded inputs.'
    valuation = state.ledger.value(day)
    flag = 'complete' if valuation.complete else 'incomplete'
    return (
        f'The known subtotal is {format(valuation.known_subtotal, "f")} '
        f'{state.ledger.reporting_currency}. The valuation is {flag}.'
    )


def _allocation_reply(state, day):
    if not day:
        return 'There is no book date in the loaded inputs. ' + ARITHMETIC_SENTENCE
    _valuation, result = _allocation_result(state, day)
    if result.status != 'complete':
        return f'The allocation status is {result.status}. ' + result.sentence
    amounts = []
    for row in result.rows:
        if row.illustrative_amount is None:
            continue
        amounts.append(f'{row.key} {format(row.illustrative_amount, "f")}')
    listed = ', '.join(amounts) if amounts else 'none'
    return f'Illustrative amounts: {listed}. ' + result.sentence


def _bars():
    return '<div id="waveform" class="waveform" aria-hidden="true">' + (
        '<i></i>' * 16
    ) + '</div>'


def render_conversation(state):
    turns = []
    for role, text in state.turns:
        css = 'question' if role == 'question' else 'reply'
        label = 'Question' if role == 'question' else 'Reply'
        turns.append(f'<p class="{css}">{label}. {escape(text)}</p>')
    transcript = ''.join(turns)
    form = (
        '<form method="post" action="/conversation">'
        '<label for="text">Question'
        '<textarea id="text" name="text"></textarea>'
        '</label>'
        '<button type="submit">Send</button>'
        '</form>'
        + _bars()
        + f'<p id="waveform-note">{_SPEECH}</p>'
        '<button type="button" id="use-microphone">Use microphone</button>'
        '<p class="dim">Speech synthesis is not implemented. This form does not call a conversation model.</p>'
        '<script src="/static/desk/waveform.js"></script>'
    )
    inner = (
        '<section><h2>Conversation</h2>'
        + transcript
        + form
        + '</section>'
    )
    return _shell(state, inner)
