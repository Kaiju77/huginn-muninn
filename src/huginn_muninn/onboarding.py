"""Entered portfolio store.

People record accounts, instruments, activities, manual balances, and prices.
This module does not fetch and does not load the synthetic fixture.
Currency rates are not recorded here. Valuation reads this book only.
Attribution reads this book only. HTTP stays in the prototype.
"""

from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
from typing import NamedTuple

from src.huginn_muninn.ledger import (
    Account,
    Buy,
    Deposit,
    Dividend,
    Instrument,
    Ledger,
    Sell,
    Withdrawal,
)


ORIGIN = 'entered'
REPORTING_CURRENCY = 'NOK'
KINDS = ('fund', 'etf', 'stock')
LEDGER_ACTIVITIES = (
    'contribution',
    'withdrawal',
    'purchase',
    'sale',
    'fee',
    'dividend',
)
ACTIVITY_WORDS = LEDGER_ACTIVITIES + ('manual balance',)
ENTERED_SENTENCE = (
    'This is your entered portfolio. Northline and Harbor on the other '
    'pages are a synthetic demo.'
)
SNAPSHOT_SENTENCE = (
    'Manual balances are snapshots. They are not a full performance record.'
)
VALUATION_SENTENCE = 'This valuation is not a recommendation.'
MISSING_PRICE_SENTENCE = 'A missing price stays unknown.'
SNAPSHOT_VALUE_SENTENCE = (
    'A manual balance is a snapshot on its date. It is not a price and '
    'it is not a full performance record.'
)
ALLOCATION_INCOMPLETE = 'Allocation is incomplete.'
ATTRIBUTION_UNAVAILABLE = 'Attribution is unavailable.'
ATTRIBUTION_SENTENCE = 'This attribution is not a recommendation.'
FEE_SENTENCE = 'A fee is cash leaving, not a market gain.'
DIVIDEND_SENTENCE = (
    'A dividend is cash received. It is not a contribution and it is not '
    'a price change.'
)
START_AFTER_END = 'The start date is after the end date.'
CASH_SNAPSHOT_NOT_ADDED = 'A cash snapshot is not added to ledger cash.'
NO_SNAPSHOT = 'No snapshot on this date'
PRICE_CURRENCY_MISMATCH = (
    'The price currency does not match the listing currency.'
)
AMBIGUOUS_PRICE = 'The price is ambiguous.'
FRESH_PRICE_DAYS = 7
INCOMPLETE_IDENTIFICATION = 'identification is incomplete'
QUANTITY_CONFLICT = (
    'This holding already has a quantity. A manual balance is not a '
    'second quantity.'
)
MANUAL_BALANCE_CONFLICT = (
    'This holding is a manual balance. A purchase would invent a quantity.'
)
UNREADABLE = 'The entered portfolio could not be read.'

_LEDGER_SENTENCES = (
    ('unknown_account', 'That account is not in this portfolio.'),
    ('unknown_instrument', 'That instrument is not in this portfolio.'),
    ('duplicate_id', 'This entry was already recorded.'),
    ('out_of_order', 'This date is earlier than the latest recorded activity.'),
    ('invalid_date', 'Enter a real date.'),
    ('blank_provenance', 'Say where this came from.'),
    ('non_decimal', 'The amount must be a decimal number.'),
    ('non_finite', 'The amount must be a finite number.'),
    ('non_positive', 'The amount must be greater than zero.'),
    ('negative_amount', 'The amount cannot be negative.'),
    ('insufficient_cash', 'There is not enough cash for this.'),
    ('insufficient_quantity', 'There is not enough of this holding to sell.'),
    ('no_position', 'A dividend needs an existing holding.'),
)

_ACTIVITY_FIELDS = {
    'contribution': ('currency', 'amount'),
    'withdrawal': ('currency', 'amount'),
    'fee': ('currency', 'amount'),
    'dividend': ('instrument', 'currency', 'amount'),
    'purchase': ('instrument', 'quantity', 'cash_currency', 'cash_amount', 'fee'),
    'sale': ('instrument', 'quantity', 'cash_currency', 'cash_amount', 'fee'),
}


class EntryResult(NamedTuple):
    accepted: bool
    message: str
    reasons: tuple
    identity: str


class ValueLine(NamedTuple):
    kind: str
    account: str
    identity: str
    currency: str
    amount: object
    known: bool
    freshness: str
    detail: str


class HistoryPoint(NamedTuple):
    on_date: str
    known_nok_subtotal: Decimal
    unknown_count: int


class ValueReport(NamedTuple):
    on_date: str
    lines: tuple
    known_nok_subtotal: Decimal
    unknown_count: int
    allocation_complete: bool
    shares: tuple
    history: tuple
    error: str
    note: str = ''


class AttributionReport(NamedTuple):
    start_date: str
    end_date: str
    start_value: object
    end_value: object
    contributions: object
    withdrawals: object
    fees: object
    dividends: object
    price_change: object
    error: str
    unavailable: bool


def default_book_path(checkout):
    return Path(checkout) / 'var' / 'entered-portfolio' / 'book.json'


def display_activity(activity):
    if activity == 'fee':
        return 'Fee'
    return activity


def explain(reasons):
    """Sentences for ledger reason codes. The codes stay out of the sentence."""
    remaining = set(reasons)
    sentences = []
    for code, sentence in _LEDGER_SENTENCES:
        if code in remaining:
            sentences.append(sentence)
            remaining.remove(code)
    if remaining or not sentences:
        sentences.append('The entry was not recorded.')
    return ' '.join(sentences)


def isin_is_valid(value):
    """ISO 6166 check digit over the first 11 characters.

    Letters A=10 through Z=35 are expanded, then from the right every
    second digit is doubled, starting with the rightmost digit. The 12th
    character must be (10 - sum mod 10) mod 10. US0378331005 is valid.
    US0378331006 is not.
    """
    if not isinstance(value, str) or len(value) != 12:
        return False
    digits = _isin_digits(value[:11])
    if digits is None:
        return False
    check_char = value[11]
    if check_char < '0' or check_char > '9':
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 0:
            number *= 2
        total += (number // 10) + (number % 10)
    check = (10 - (total % 10)) % 10
    return check_char == str(check)


def _isin_digits(body):
    pieces = []
    for char in body:
        if '0' <= char <= '9':
            pieces.append(char)
        elif 'A' <= char <= 'Z':
            pieces.append(str(ord(char) - ord('A') + 10))
        else:
            return None
    return ''.join(pieces)


def _empty_document():
    return {
        'origin': ORIGIN,
        'reporting_currency': REPORTING_CURRENCY,
        'accounts': [],
        'instruments': [],
        'activities': [],
        'manual_balances': [],
    }


def _valuation_context():
    """28 significant digits. Rounding applies only past that precision."""
    return Context(prec=28, rounding=ROUND_HALF_EVEN)


def _multiply(left, right):
    with localcontext(_valuation_context()):
        return left * right


def _divide(left, right):
    with localcontext(_valuation_context()):
        return left / right


def _sum_decimals(amounts):
    total = Decimal(0)
    with localcontext(_valuation_context()):
        for amount in amounts:
            total = total + amount
    return total


def _blank_report(message):
    return ValueReport('', (), Decimal(0), 0, False, (), (), message)


def _cash_snapshot_overlaps(line, ledger_cash):
    """A known cash snapshot for an account that also has ledger cash."""
    return (
        line.kind == 'snapshot'
        and line.identity == 'cash'
        and line.known
        and line.amount is not None
        and (line.account, line.currency) in ledger_cash
    )


def _blank_attribution(message, start='', end=''):
    return AttributionReport(
        start,
        end,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        message,
        False,
    )


def _unavailable_attribution(start, end):
    return AttributionReport(
        start,
        end,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        '',
        True,
    )


def _boundary_date(value, label):
    day, message = _clean_date(value)
    if message == 'Enter the date.':
        return None, f'Enter the {label} date.'
    if message is not None:
        return None, message
    return date.fromisoformat(day), None


def _in_window(event_date, start_on, end_on):
    """Activities strictly after the start date and on or before the end."""
    return start_on < date.fromisoformat(event_date) <= end_on


def _flow_is_nok(row):
    activity = row['activity']
    if activity in {'contribution', 'withdrawal', 'fee', 'dividend'}:
        return row.get('currency') == REPORTING_CURRENCY
    if activity in {'purchase', 'sale'}:
        return row.get('cash_currency') == REPORTING_CURRENCY
    return False


def _report_is_attributed(report):
    """Both dates must be known NOK cash or quantity times one price."""
    if report.error or report.note == CASH_SNAPSHOT_NOT_ADDED:
        return False
    for line in report.lines:
        if line.kind == 'snapshot':
            return False
        if not line.known or line.amount is None:
            return False
        if line.currency != REPORTING_CURRENCY:
            return False
    return True


def _attributed_change(
    end_value,
    start_value,
    contributions,
    withdrawals,
    fees,
    dividends,
):
    """end - start - contributions + withdrawals + fees - dividends."""
    with localcontext(_valuation_context()):
        change = end_value - start_value
        change = change - contributions
        change = change + withdrawals
        change = change + fees
        change = change - dividends
        return change


def price_freshness(valuation_date, evidence_date, selected_date):
    """Label one stored price against the selected date.

    The selected date is the only clock. A price is fresh when both of
    its dates are on or before that date and the gap from the valuation
    date is at most 7 days. A later valuation date, a later evidence
    date, and an older valuation date are future_valuation,
    future_evidence, and stale. Those labels do not remove the price.
    """
    selected = date.fromisoformat(selected_date)
    valuation = date.fromisoformat(valuation_date)
    evidence = date.fromisoformat(evidence_date)
    flags = []
    if valuation > selected:
        flags.append('future_valuation')
    if evidence > selected:
        flags.append('future_evidence')
    if (selected - valuation).days > FRESH_PRICE_DAYS:
        flags.append('stale')
    if not flags:
        flags.append('fresh')
    return tuple(flags)


def _sentence(code):
    for candidate, sentence in _LEDGER_SENTENCES:
        if candidate == code:
            return sentence
    return 'The entry was not recorded.'


def _fail(message, reasons=()):
    return EntryResult(False, message, tuple(reasons), '')


def _ok(identity):
    return EntryResult(True, 'Saved.', (), identity)


def _stored_amount(number):
    return format(number, 'f')


def _finite_decimal(raw):
    if isinstance(raw, Decimal):
        number = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if text == '':
            return None, 'missing'
        try:
            number = Decimal(text)
        except InvalidOperation:
            return None, 'non_decimal'
    else:
        return None, 'non_decimal'
    if not number.is_finite():
        return None, 'non_finite'
    return number, None


def _amount_problem(raw, missing_message):
    number, code = _finite_decimal(raw)
    if code == 'missing':
        return missing_message, None, None
    if code in {'non_decimal', 'non_finite'}:
        return _sentence(code), code, None
    return None, None, number


def _currency_text(value):
    if not isinstance(value, str) or value.strip() == '':
        return None
    return value


def _clean_date(value):
    if not isinstance(value, str) or value.strip() == '':
        return None, 'Enter the date.'
    text = value.strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        return None, _sentence('invalid_date')
    return text, None


def _clean_provenance(value):
    if not isinstance(value, str) or value.strip() == '':
        return None
    return value.strip()


def _event_from_activity(row):
    activity = row['activity']
    if activity == 'contribution':
        return Deposit(
            row['event_id'],
            row['account'],
            row['currency'],
            Decimal(row['amount']),
            row['event_date'],
            row['provenance'],
        )
    if activity in {'withdrawal', 'fee'}:
        return Withdrawal(
            row['event_id'],
            row['account'],
            row['currency'],
            Decimal(row['amount']),
            row['event_date'],
            row['provenance'],
        )
    if activity == 'purchase':
        return Buy(
            row['event_id'],
            row['account'],
            row['instrument'],
            Decimal(row['quantity']),
            row['cash_currency'],
            Decimal(row['cash_amount']),
            Decimal(row['fee']),
            row['event_date'],
            row['provenance'],
        )
    if activity == 'sale':
        return Sell(
            row['event_id'],
            row['account'],
            row['instrument'],
            Decimal(row['quantity']),
            row['cash_currency'],
            Decimal(row['cash_amount']),
            Decimal(row['fee']),
            row['event_date'],
            row['provenance'],
        )
    if activity == 'dividend':
        return Dividend(
            row['event_id'],
            row['account'],
            row['instrument'],
            row['currency'],
            Decimal(row['amount']),
            row['event_date'],
            row['provenance'],
        )
    raise ValueError('activity is not an entered ledger activity')


def replay(document):
    """Build a ledger from entered activities. Prices and rates stay empty."""
    ledger = Ledger(document['reporting_currency'])
    for account in document['accounts']:
        ledger.add_account(Account(account['identity']))
    for instrument in document['instruments']:
        ledger.add_instrument(
            Instrument(instrument['identity'], instrument['listing_currency'])
        )
    postings = []
    for row in document['activities']:
        postings.append(ledger.record(_event_from_activity(row)))
    return ledger, tuple(postings)


def _string_field(row, field):
    value = row.get(field)
    if not isinstance(value, str):
        raise ValueError(field)
    return value


def _validate_document(raw):
    if not isinstance(raw, dict):
        raise ValueError('document')
    if raw.get('origin') != ORIGIN:
        raise ValueError('origin')
    if raw.get('reporting_currency') != REPORTING_CURRENCY:
        raise ValueError('reporting_currency')
    for key in ('accounts', 'instruments', 'activities', 'manual_balances'):
        if not isinstance(raw.get(key), list):
            raise ValueError(key)
    for account in raw['accounts']:
        if not isinstance(account, dict) or account.get('origin') != ORIGIN:
            raise ValueError('account')
        for field in ('identity', 'institution', 'name'):
            if _string_field(account, field).strip() == '':
                raise ValueError(field)
    for instrument in raw['instruments']:
        if not isinstance(instrument, dict) or instrument.get('origin') != ORIGIN:
            raise ValueError('instrument')
        for field in (
            'identity',
            'display_name',
            'kind',
            'listing_currency',
            'isin',
        ):
            _string_field(instrument, field)
        if instrument['kind'] not in KINDS:
            raise ValueError('kind')
        if instrument['listing_currency'].strip() == '':
            raise ValueError('listing_currency')
        if instrument['isin'] == '':
            if instrument['identity'].strip() == '':
                raise ValueError('identity')
        elif instrument['identity'] != instrument['isin']:
            raise ValueError('isin identity')
        elif not isin_is_valid(instrument['isin']):
            raise ValueError('isin')
    for activity in raw['activities']:
        if not isinstance(activity, dict) or activity.get('origin') != ORIGIN:
            raise ValueError('activity')
        kind = _string_field(activity, 'activity')
        if kind not in _ACTIVITY_FIELDS:
            raise ValueError('activity')
        for field in ('event_id', 'account', 'event_date', 'provenance'):
            if _string_field(activity, field).strip() == '':
                raise ValueError(field)
        for field in _ACTIVITY_FIELDS[kind]:
            if _string_field(activity, field).strip() == '':
                raise ValueError(field)
    for balance in raw['manual_balances']:
        if not isinstance(balance, dict) or balance.get('origin') != ORIGIN:
            raise ValueError('manual balance')
        holding = _string_field(balance, 'holding')
        if holding not in {'cash', 'instrument'}:
            raise ValueError('holding')
        for field in ('account', 'amount', 'currency', 'as_of', 'provenance'):
            if _string_field(balance, field).strip() == '':
                raise ValueError(field)
        instrument = _string_field(balance, 'instrument')
        if holding == 'cash' and instrument != '':
            raise ValueError('instrument')
        if holding == 'instrument' and instrument.strip() == '':
            raise ValueError('instrument')
    listings = {
        instrument['identity']: instrument['listing_currency']
        for instrument in raw['instruments']
    }
    stored_prices = raw.get('prices', [])
    if not isinstance(stored_prices, list):
        raise ValueError('prices')
    for price in stored_prices:
        if not isinstance(price, dict) or price.get('origin') != ORIGIN:
            raise ValueError('price')
        instrument = _string_field(price, 'instrument')
        if instrument not in listings:
            raise ValueError('price instrument')
        amount, code = _finite_decimal(price.get('amount'))
        if code is not None or amount < 0:
            raise ValueError('price amount')
        currency = _string_field(price, 'currency')
        if currency != listings[instrument]:
            raise ValueError('price currency')
        for field in ('valuation_date', 'evidence_date'):
            text, problem = _clean_date(price.get(field))
            if text is None or problem is not None:
                raise ValueError(field)
        if _clean_provenance(price.get('provenance')) is None:
            raise ValueError('price provenance')
    ledger, postings = replay(raw)
    if any(not posting.accepted for posting in postings):
        raise ValueError('rejected activity')
    return raw, ledger


class EnteredPortfolio:
    """JSON book chosen by the caller. An empty file is a valid book."""

    def __init__(self, path):
        self.path = Path(path)
        self.load_error = ''
        self.document = _empty_document()
        self._load()

    def _load(self):
        if not self.path.is_file():
            self.document = _empty_document()
            self.load_error = ''
            return
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            document, _ledger = _validate_document(raw)
        except (OSError, json.JSONDecodeError, ValueError, TypeError, InvalidOperation):
            self.document = _empty_document()
            self.load_error = UNREADABLE
            return
        self.document = document
        self.load_error = ''

    @property
    def reporting_currency(self):
        return self.document['reporting_currency']

    @property
    def accounts(self):
        return tuple(self.document['accounts'])

    @property
    def instruments(self):
        return tuple(self.document['instruments'])

    @property
    def activities(self):
        return tuple(self.document['activities'])

    @property
    def manual_balances(self):
        return tuple(self.document['manual_balances'])

    @property
    def prices(self):
        return tuple(self.document.get('prices', ()))

    def account_label(self, identity):
        for account in self.accounts:
            if account['identity'] == identity:
                return f"{account['institution']} {account['name']}"
        return 'Unknown account'

    def instrument_label(self, identity):
        for instrument in self.instruments:
            if instrument['identity'] == identity:
                return instrument['display_name']
        return 'Unknown instrument'

    def latest_activity_date(self):
        dates = [row['event_date'] for row in self.activities]
        if not dates:
            return None
        return max(dates)

    def ledger(self):
        if self.load_error:
            return None
        ledger, postings = replay(self.document)
        if any(not posting.accepted for posting in postings):
            return None
        return ledger

    def recorded_events(self):
        ledger = self.ledger()
        if ledger is None:
            return ()
        return tuple(ledger._accepted)

    def books(self):
        ledger = self.ledger()
        day = self.latest_activity_date()
        if ledger is None or day is None:
            return None
        return ledger.books(day)

    def add_account(self, institution, name):
        refused = self._refused()
        if refused is not None:
            return refused
        problems = []
        if not isinstance(institution, str) or institution.strip() == '':
            problems.append('Enter the institution.')
        if not isinstance(name, str) or name.strip() == '':
            problems.append('Enter the account name.')
        if problems:
            if len(problems) == 2:
                return _fail('Enter the institution and the account name.')
            return _fail(problems[0])
        institution = institution.strip()
        name = name.strip()
        for account in self.accounts:
            if account['institution'] == institution and account['name'] == name:
                return _fail(
                    'An account with this institution and name is already entered.'
                )
        identity = self._new_id('entered-account')
        staged = deepcopy(self.document)
        staged['accounts'].append({
            'origin': ORIGIN,
            'identity': identity,
            'institution': institution,
            'name': name,
        })
        self._commit(staged)
        return _ok(identity)

    def add_instrument(self, display_name, kind, listing_currency, isin=''):
        refused = self._refused()
        if refused is not None:
            return refused
        if not isinstance(display_name, str) or display_name.strip() == '':
            return _fail('Enter a name for the instrument.')
        if not isinstance(kind, str) or kind.strip() not in KINDS:
            return _fail('Kind is fund, etf, or stock.')
        currency = _currency_text(listing_currency)
        if currency is None:
            return _fail('Enter the listing currency.')
        if isin is None:
            isin = ''
        if not isinstance(isin, str):
            return _fail('That ISIN is not valid.')
        text = isin.strip()
        if text == '':
            identity = self._new_id('entered-instrument')
            stored_isin = ''
        elif not isin_is_valid(text):
            return _fail('That ISIN is not valid.')
        else:
            for instrument in self.instruments:
                if instrument['isin'] == text:
                    return _fail('An instrument with this ISIN is already entered.')
            identity = text
            stored_isin = text
        staged = deepcopy(self.document)
        staged['instruments'].append({
            'origin': ORIGIN,
            'identity': identity,
            'display_name': display_name.strip(),
            'kind': kind.strip(),
            'listing_currency': currency,
            'isin': stored_isin,
        })
        self._commit(staged)
        return _ok(identity)

    def add_activity(
        self,
        activity,
        account,
        event_date,
        provenance,
        currency='',
        amount='',
        instrument='',
        quantity='',
        cash_currency='',
        cash_amount='',
        fee='',
    ):
        refused = self._refused()
        if refused is not None:
            return refused
        if activity not in LEDGER_ACTIVITIES:
            return _fail(
                'Choose contribution, withdrawal, purchase, sale, fee, '
                'dividend, or manual balance.'
            )
        problems = []
        reasons = []
        if self._find_account(account) is None:
            problems.append('Choose an account that you have entered.')
        day, date_message = _clean_date(event_date)
        if date_message is not None:
            problems.append(date_message)
            if date_message == _sentence('invalid_date'):
                reasons.append('invalid_date')
        source = _clean_provenance(provenance)
        if source is None:
            problems.append(_sentence('blank_provenance'))
            reasons.append('blank_provenance')
        values = {}
        if activity in {'contribution', 'withdrawal', 'fee', 'dividend'}:
            self._take_amount(problems, reasons, values, 'amount', amount, 'Enter the amount.')
            self._take_currency(problems, values, 'currency', currency, 'Enter the currency.')
        if activity == 'dividend':
            if self._find_instrument(instrument) is None:
                problems.append('Choose an instrument that you have entered.')
            else:
                values['instrument'] = instrument
        if activity in {'purchase', 'sale'}:
            if self._find_instrument(instrument) is None:
                problems.append('Choose an instrument that you have entered.')
            else:
                values['instrument'] = instrument
            self._take_amount(
                problems,
                reasons,
                values,
                'quantity',
                quantity,
                'Enter the quantity.',
            )
            self._take_amount(
                problems,
                reasons,
                values,
                'cash_amount',
                cash_amount,
                'Enter the cash amount.',
            )
            self._take_currency(
                problems,
                values,
                'cash_currency',
                cash_currency,
                'Enter the cash currency.',
            )
            self._take_amount(
                problems,
                reasons,
                values,
                'fee',
                fee,
                'Enter a fee of zero or more.',
            )
        if problems:
            return _fail(' '.join(problems), reasons)
        if (
            activity == 'purchase'
            and self._manual_for_instrument(values['instrument'])
        ):
            return _fail(MANUAL_BALANCE_CONFLICT)
        event_id = self._new_id('entered-activity')
        row = {
            'origin': ORIGIN,
            'activity': activity,
            'event_id': event_id,
            'account': account,
            'event_date': day,
            'provenance': source,
        }
        if activity in {'contribution', 'withdrawal', 'fee', 'dividend'}:
            row['currency'] = values['currency']
            row['amount'] = _stored_amount(values['amount'])
        if activity == 'dividend':
            row['instrument'] = values['instrument']
        if activity in {'purchase', 'sale'}:
            row['instrument'] = values['instrument']
            row['quantity'] = _stored_amount(values['quantity'])
            row['cash_currency'] = values['cash_currency']
            row['cash_amount'] = _stored_amount(values['cash_amount'])
            row['fee'] = _stored_amount(values['fee'])
        staged = deepcopy(self.document)
        staged['activities'].append(row)
        try:
            _ledger, postings = replay(staged)
        except (ValueError, TypeError, InvalidOperation):
            return _fail('The entry was not recorded.')
        posting = postings[-1]
        if not posting.accepted:
            return _fail(explain(posting.reasons), posting.reasons)
        self._commit(staged)
        return _ok(event_id)

    def add_manual_balance(
        self,
        account,
        subject,
        amount,
        currency,
        as_of,
        provenance,
    ):
        refused = self._refused()
        if refused is not None:
            return refused
        problems = []
        reasons = []
        if self._find_account(account) is None:
            problems.append('Choose an account that you have entered.')
        day, date_message = _clean_date(as_of)
        if date_message is not None:
            problems.append(
                'Enter the as-of date.'
                if date_message == 'Enter the date.'
                else date_message
            )
            if date_message == _sentence('invalid_date'):
                reasons.append('invalid_date')
        source = _clean_provenance(provenance)
        if source is None:
            problems.append(_sentence('blank_provenance'))
            reasons.append('blank_provenance')
        values = {}
        self._take_amount(problems, reasons, values, 'amount', amount, 'Enter the amount.')
        self._take_currency(problems, values, 'currency', currency, 'Enter the currency.')
        holding = None
        instrument = ''
        if subject == 'cash':
            holding = 'cash'
        elif self._find_instrument(subject) is not None:
            holding = 'instrument'
            instrument = subject
        else:
            problems.append('Choose cash or one instrument.')
        if problems:
            return _fail(' '.join(problems), reasons)
        if holding == 'instrument' and self._has_quantity(instrument):
            return _fail(QUANTITY_CONFLICT)
        staged = deepcopy(self.document)
        staged['manual_balances'].append({
            'origin': ORIGIN,
            'account': account,
            'holding': holding,
            'instrument': instrument,
            'amount': _stored_amount(values['amount']),
            'currency': values['currency'],
            'as_of': day,
            'provenance': source,
        })
        self._commit(staged)
        return _ok('')

    def record_price(
        self,
        instrument,
        amount,
        currency,
        valuation_date,
        evidence_date,
        provenance,
    ):
        """Store one entered price. A second price on the same date stays."""
        refused = self._refused()
        if refused is not None:
            return refused
        problems = []
        reasons = []
        found = self._find_instrument(instrument)
        if found is None:
            problems.append('Choose an instrument that you have entered.')
        values = {}
        self._take_amount(
            problems,
            reasons,
            values,
            'amount',
            amount,
            'Enter the amount.',
        )
        if 'amount' in values and values['amount'] < 0:
            problems.append(_sentence('negative_amount'))
            reasons.append('negative_amount')
            del values['amount']
        elif 'amount' in values and values['amount'] == 0:
            values['amount'] = Decimal(0)
        price_currency = _currency_text(currency)
        if price_currency is None:
            problems.append('Enter the currency.')
        elif found is not None and price_currency != found['listing_currency']:
            problems.append(PRICE_CURRENCY_MISMATCH)
            reasons.append('currency_mismatch')
        valuation_day, valuation_message = _clean_date(valuation_date)
        if valuation_message == 'Enter the date.':
            problems.append('Enter the valuation date.')
        elif valuation_message is not None:
            problems.append(valuation_message)
            reasons.append('invalid_date')
        evidence_day, evidence_message = _clean_date(evidence_date)
        if evidence_message == 'Enter the date.':
            problems.append('Enter the evidence date.')
        elif evidence_message is not None:
            problems.append(evidence_message)
            reasons.append('invalid_date')
        source = _clean_provenance(provenance)
        if source is None:
            problems.append(_sentence('blank_provenance'))
            reasons.append('blank_provenance')
        if problems:
            return _fail(' '.join(problems), reasons)
        staged = deepcopy(self.document)
        stored = list(staged.get('prices', []))
        stored.append({
            'origin': ORIGIN,
            'instrument': found['identity'],
            'amount': _stored_amount(values['amount']),
            'currency': price_currency,
            'valuation_date': valuation_day,
            'evidence_date': evidence_day,
            'provenance': source,
        })
        staged['prices'] = stored
        try:
            self._commit(staged)
        except (ValueError, TypeError, InvalidOperation, OSError):
            return _fail('The entry was not recorded.')
        return _ok('')

    def value_on(self, on_date):
        """Value this entered book on one selected date.

        Cash stays at face in its own currency. A quantity uses one price
        whose valuation date is that date and whose currency is the listing
        currency. A manual balance is used only on its as-of date. A cash
        snapshot on that date stays on its own line. When that account and
        currency also have ledger cash, the snapshot is not added to the
        known NOK subtotal and the report is incomplete. A snapshot whose
        ledger cash is zero can be a known amount. Nothing here converts
        currencies or fills in a missing price.
        """
        if self.load_error:
            return _blank_report(self.load_error)
        day, message = _clean_date(on_date)
        if message is not None:
            if message == 'Enter the date.':
                return _blank_report('Enter the date.')
            return _blank_report(message)
        ledger = self.ledger()
        if ledger is None:
            return _blank_report(UNREADABLE)
        (
            lines,
            subtotal,
            unknown,
            complete,
            shares,
            cash_overlap,
        ) = self._valuate(ledger, day)
        history = []
        for historic in self._history_dates(day):
            if historic == day:
                history.append(HistoryPoint(historic, subtotal, unknown))
                continue
            (
                _lines,
                other_total,
                other_unknown,
                _complete,
                _shares,
                _overlap,
            ) = self._valuate(
                ledger,
                historic,
            )
            history.append(HistoryPoint(historic, other_total, other_unknown))
        note = CASH_SNAPSHOT_NOT_ADDED if cash_overlap else ''
        return ValueReport(
            day,
            lines,
            subtotal,
            unknown,
            complete,
            shares,
            tuple(history),
            '',
            note,
        )

    def attribute(self, start, end):
        """Separate flows from the change in value between two dates.

        Flows are activities strictly after the start date and on or
        before the end date. A contribution, withdrawal, fee, or dividend
        uses its own amount. A purchase or a sale stays inside the two
        valuations; only its fee is a fee. A fee is cash leaving. A
        dividend is cash received. Nothing here converts currencies or
        fills in a missing price.
        """
        if self.load_error:
            return _blank_attribution(self.load_error)
        start_on, start_message = _boundary_date(start, 'start')
        end_on, end_message = _boundary_date(end, 'end')
        if start_message is not None or end_message is not None:
            return _blank_attribution(
                ' '.join(
                    message
                    for message in (start_message, end_message)
                    if message is not None
                )
            )
        start_day = start_on.isoformat()
        end_day = end_on.isoformat()
        if start_on > end_on:
            return _blank_attribution(START_AFTER_END, start_day, end_day)
        start_report = self.value_on(start_day)
        end_report = self.value_on(end_day)
        if not self._can_attribute(start_on, end_on, start_report, end_report):
            return _unavailable_attribution(start_day, end_day)
        contributions, withdrawals, fees, dividends = self._window_totals(
            start_on,
            end_on,
        )
        return AttributionReport(
            start_day,
            end_day,
            start_report.known_nok_subtotal,
            end_report.known_nok_subtotal,
            contributions,
            withdrawals,
            fees,
            dividends,
            _attributed_change(
                end_report.known_nok_subtotal,
                start_report.known_nok_subtotal,
                contributions,
                withdrawals,
                fees,
                dividends,
            ),
            '',
            False,
        )

    def _can_attribute(self, start_on, end_on, start_report, end_report):
        if self.manual_balances:
            return False
        if (
            not _report_is_attributed(start_report)
            or not _report_is_attributed(end_report)
        ):
            return False
        for row in self.activities:
            if _in_window(row['event_date'], start_on, end_on) and not _flow_is_nok(row):
                return False
        return True

    def _window_totals(self, start_on, end_on):
        contributions = []
        withdrawals = []
        fees = []
        dividends = []
        for row in self.activities:
            if not _in_window(row['event_date'], start_on, end_on):
                continue
            activity = row['activity']
            if activity == 'contribution':
                contributions.append(Decimal(row['amount']))
            elif activity == 'withdrawal':
                withdrawals.append(Decimal(row['amount']))
            elif activity == 'fee':
                fees.append(Decimal(row['amount']))
            elif activity == 'dividend':
                dividends.append(Decimal(row['amount']))
            elif activity in {'purchase', 'sale'}:
                fees.append(Decimal(row['fee']))
        return (
            _sum_decimals(contributions),
            _sum_decimals(withdrawals),
            _sum_decimals(fees),
            _sum_decimals(dividends),
        )

    def _history_dates(self, selected):
        found = {selected}
        for row in self.activities:
            found.add(row['event_date'])
        return tuple(sorted(found))

    def _valuate(self, ledger, day):
        books = ledger.books(day)
        manual_instruments = {
            row['instrument']
            for row in self.manual_balances
            if row['holding'] == 'instrument'
        }
        lines = []
        ledger_cash = set()
        for cash in books.cash:
            lines.append(ValueLine(
                'cash',
                cash.account,
                cash.currency,
                cash.currency,
                cash.amount,
                True,
                '',
                '',
            ))
            if cash.amount != 0:
                ledger_cash.add((cash.account, cash.currency))
        for position in books.positions:
            if position.instrument in manual_instruments:
                continue
            lines.append(self._quantity_line(position, day))
        lines.extend(self._snapshot_lines(day))
        cash_overlap = False
        nok_amounts = []
        for line in lines:
            if _cash_snapshot_overlaps(line, ledger_cash):
                cash_overlap = True
                continue
            if (
                line.known
                and line.currency == REPORTING_CURRENCY
                and line.amount is not None
            ):
                nok_amounts.append(line.amount)
        subtotal = _sum_decimals(nok_amounts)
        unknown = sum(1 for line in lines if not line.known)
        complete = not cash_overlap and all(
            line.known and line.currency == REPORTING_CURRENCY
            for line in lines
        )
        shares = ()
        if complete and subtotal != 0:
            shares = tuple(_divide(line.amount, subtotal) for line in lines)
        return lines, subtotal, unknown, complete, shares, cash_overlap

    def _quantity_line(self, position, day):
        instrument = self._find_instrument(position.instrument)
        listing = '' if instrument is None else instrument['listing_currency']
        matches = [
            row for row in self.prices
            if row['instrument'] == position.instrument
            and row['valuation_date'] == day
            and row['currency'] == listing
        ]
        if len(matches) == 1:
            price = matches[0]
            flags = price_freshness(
                price['valuation_date'],
                price['evidence_date'],
                day,
            )
            return ValueLine(
                'quantity',
                position.account,
                position.instrument,
                listing,
                _multiply(position.quantity, Decimal(price['amount'])),
                True,
                ' '.join(flags),
                '',
            )
        if len(matches) > 1:
            return ValueLine(
                'quantity',
                position.account,
                position.instrument,
                listing,
                None,
                False,
                '',
                AMBIGUOUS_PRICE,
            )
        return ValueLine(
            'quantity',
            position.account,
            position.instrument,
            listing,
            None,
            False,
            '',
            'unknown',
        )

    def _snapshot_lines(self, day):
        groups = []
        rows_for = {}
        for row in self.manual_balances:
            if row['holding'] == 'cash':
                key = ('cash', row['account'], 'cash', row['currency'])
            else:
                key = ('instrument', row['account'], row['instrument'], '')
            if key not in rows_for:
                rows_for[key] = []
                groups.append(key)
            rows_for[key].append(row)
        lines = []
        for key in groups:
            kind, account, identity, currency = key
            matched = [
                row for row in rows_for[key]
                if row['as_of'] == day
            ]
            if len(matched) == 1:
                row = matched[0]
                lines.append(ValueLine(
                    'snapshot',
                    account,
                    identity,
                    row['currency'],
                    Decimal(row['amount']),
                    True,
                    '',
                    'snapshot',
                ))
            elif len(matched) == 0:
                lines.append(ValueLine(
                    'snapshot',
                    account,
                    identity,
                    currency,
                    None,
                    False,
                    '',
                    NO_SNAPSHOT,
                ))
            else:
                lines.append(ValueLine(
                    'snapshot',
                    account,
                    identity,
                    currency,
                    None,
                    False,
                    '',
                    'The snapshot is ambiguous.',
                ))
        return lines

    def _refused(self):
        if self.load_error:
            return _fail(self.load_error)
        return None

    def _find_account(self, identity):
        for account in self.accounts:
            if account['identity'] == identity:
                return account
        return None

    def _find_instrument(self, identity):
        if not isinstance(identity, str) or identity == '':
            return None
        for instrument in self.instruments:
            if instrument['identity'] == identity:
                return instrument
        return None

    def _manual_for_instrument(self, identity):
        for row in self.manual_balances:
            if row['holding'] == 'instrument' and row['instrument'] == identity:
                return True
        return False

    def _has_quantity(self, identity):
        snapshot = self.books()
        if snapshot is None:
            return False
        for position in snapshot.positions:
            if position.instrument == identity:
                return True
        return False

    def _take_amount(self, problems, reasons, values, key, raw, missing_message):
        message, code, number = _amount_problem(raw, missing_message)
        if message is not None:
            problems.append(message)
            if code is not None:
                reasons.append(code)
            return
        values[key] = number

    def _take_currency(self, problems, values, key, raw, message):
        currency = _currency_text(raw)
        if currency is None:
            problems.append(message)
            return
        values[key] = currency

    def _new_id(self, prefix):
        used = set()
        for account in self.accounts:
            used.add(account['identity'])
        for instrument in self.instruments:
            used.add(instrument['identity'])
        for activity in self.activities:
            used.add(activity['event_id'])
        number = 1
        while f'{prefix}-{number}' in used:
            number += 1
        return f'{prefix}-{number}'

    def _commit(self, document):
        if self.load_error:
            raise RuntimeError('refusing to overwrite an unreadable book')
        if not document.get('prices'):
            document.pop('prices', None)
        _validate_document(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(document, indent=2, ensure_ascii=False) + '\n'
        self.path.write_text(text, encoding='utf-8')
        self.document = document
