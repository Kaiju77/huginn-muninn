#!/usr/bin/env python3
"""End-to-end check of the entered-portfolio workflow over real HTTP.

Starts the prototype server on 127.0.0.1 with an ephemeral port and a
temporary store, then drives the routes a person would use:

  account -> instrument -> contribution -> purchase with fee
  -> valuation before prices (must stay unknown)
  -> record two prices -> valuation (known NOK subtotal)
  -> performance split (contributions, fees, price change)

All data is synthetic and lives in a temporary directory. Nothing in
fixtures/ or var/ is written. No network beyond loopback.

Exit code 0 when every step passes, 1 otherwise.
"""

import re
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.serve_prototype import PrototypeHandler  # noqa: E402
from src.huginn_muninn.prototype import open_state  # noqa: E402

FIXTURE = _ROOT / 'fixtures' / 'synthetic_portfolio.json'


class _Quiet(PrototypeHandler):
    def log_message(self, *args):
        pass


def _request(base, method, path, form=None):
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode('utf-8')
    req = urllib.request.Request(base + path, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode('utf-8')


def run(verbose=True):
    """Run the workflow. Return a list of (step, ok, detail)."""
    results = []

    def check(step, ok, detail=''):
        results.append((step, bool(ok), detail))
        if verbose:
            print(f"{'PASS' if ok else 'FAIL'}  {step}{'  - ' + detail if detail and not ok else ''}")
        return ok

    fixture_before = FIXTURE.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        server = HTTPServer(('127.0.0.1', 0), _Quiet)
        server.prototype_state = open_state(
            _ROOT, tmp / 'synthetic-book.json', tmp / 'book.json'
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_address[1]}'
        try:
            status, body = _request(base, 'GET', '/portfolio')
            check('GET /portfolio on an empty book', status == 200, f'status {status}')

            status, body = _request(base, 'POST', '/portfolio', {
                'action': 'account', 'institution': 'Test Bank', 'account_name': 'Main',
            })
            account = re.search(r'value="(entered-account-\d+)"', body)
            check('POST account', status == 200 and account, f'status {status}')
            account = account.group(1) if account else ''

            status, body = _request(base, 'POST', '/portfolio', {
                'action': 'instrument', 'display_name': 'Test fund',
                'kind': 'fund', 'listing_currency': 'NOK', 'isin': '',
            })
            instrument = re.search(r'value="(entered-instrument-\d+)"', body)
            check('POST instrument', status == 200 and instrument, f'status {status}')
            instrument = instrument.group(1) if instrument else ''

            status, _ = _request(base, 'POST', '/portfolio', {
                'action': 'activity', 'activity': 'contribution', 'account': account,
                'event_date': '2026-05-01', 'provenance': 'statement',
                'currency': 'NOK', 'amount': '1000',
            })
            check('POST contribution 1000 NOK on 2026-05-01', status == 200, f'status {status}')

            status, _ = _request(base, 'POST', '/portfolio', {
                'action': 'activity', 'activity': 'purchase', 'account': account,
                'event_date': '2026-05-02', 'provenance': 'statement',
                'instrument': instrument, 'quantity': '10',
                'cash_currency': 'NOK', 'cash_amount': '500', 'fee': '10',
            })
            check('POST purchase 10 units for 500 NOK + 10 fee', status == 200, f'status {status}')

            status, body = _request(base, 'GET', '/portfolio/valuation?date=2026-05-03')
            check(
                'Valuation without a price keeps the price unknown',
                status == 200
                and 'A missing price stays unknown.' in body
                and 'Allocation is incomplete.' in body,
                f'status {status}',
            )

            for day, amount in (('2026-05-02', '50'), ('2026-05-03', '60')):
                status, _ = _request(base, 'POST', '/portfolio/valuation', {
                    'action': 'price', 'instrument': instrument, 'amount': amount,
                    'currency': 'NOK', 'valuation_date': day, 'evidence_date': day,
                    'provenance': 'statement',
                })
                check(f'POST price {amount} NOK on {day}', status == 200, f'status {status}')

            status, body = _request(base, 'GET', '/portfolio/valuation?date=2026-05-03')
            check(
                'Valuation on 2026-05-03 = 490 cash + 10 x 60 = 1090 NOK',
                status == 200 and 'data-nok-subtotal="1090"' in body,
                f'status {status}',
            )

            status, body = _request(
                base, 'GET', '/portfolio/performance?start=2026-05-01&end=2026-05-03'
            )
            expected = {
                'data-start-value': '1000', 'data-end-value': '1090',
                'data-contributions': '0', 'data-fees': '10',
                'data-price-change': '100',
            }
            missing = [k for k, v in expected.items() if f'{k}="{v}"' not in body]
            check(
                'Performance 05-01..05-03: fee 10, price change 100',
                status == 200 and not missing and 'Attribution is unavailable.' not in body,
                f'status {status}, mismatched {missing}',
            )

            check('Store written only to the temp dir', (tmp / 'book.json').exists())
        finally:
            server.shutdown()
            server.server_close()
    check('Synthetic fixture unchanged', FIXTURE.read_bytes() == fixture_before)
    return results


def main():
    results = run()
    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} steps passed.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
