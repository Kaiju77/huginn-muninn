"""Entered portfolio store.

People record accounts, instruments, activities, and manual balances.
This module does not fetch and does not load the synthetic fixture.
Prices and currency rates are not recorded here. HTTP stays in the prototype.
"""

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
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
        _validate_document(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(document, indent=2, ensure_ascii=False) + '\n'
        self.path.write_text(text, encoding='utf-8')
        self.document = document
