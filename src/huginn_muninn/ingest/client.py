"""Allowlisted HTTP client for an explicit refresh.

urllib is imported only inside the live transport. Tests inject a fake
transport, and that fake is the only transport the unittest suite calls.
"""

from datetime import datetime, timezone
from typing import NamedTuple
from urllib.parse import urlsplit
import asyncio
import inspect
import time

from src.huginn_muninn.ingest.cache import write_response


ALLOWLIST = frozenset((
    'data.norges-bank.no',
    'data-api.ecb.europa.eu',
    'data.ssb.no',
    'data.sec.gov',
))

RETRY_STATUSES = frozenset((429, 500, 502, 503, 504))
TIMEOUT_SECONDS = 15
MIN_INTERVAL_SECONDS = 2
MAX_RETRIES = 2
MAX_BODY_BYTES = 1000000
STRUCTURED_ERRORS = frozenset((
    'not_allowlisted',
    'timeout',
    'http_status',
    'parse_error',
    'configuration_required',
    'body_too_large',
))


class TransportError(Exception):
    def __init__(self, detail):
        super().__init__(detail)
        self.detail = detail


class TransportResponse(NamedTuple):
    status: int
    body: bytes
    origin: str


class FetchRequest(NamedTuple):
    url: str
    timeout: int
    headers: tuple


class FetchResult(NamedTuple):
    ok: bool
    reason: str
    status: object
    url: str
    body: bytes
    retrieved_at: str
    attempts: int
    origin: str
    detail: str


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Client:
    """One explicit fetch at a time. This does not start a scheduler."""

    def __init__(self, transport, cache_dir, clock=None, sleep=None, retrieved_at=None):
        self.transport = transport
        self.cache_dir = cache_dir
        self.clock = clock or time.monotonic
        self.sleep = sleep or asyncio.sleep
        self.retrieved_at = retrieved_at
        self._last = {}

    def fetch(self, url, headers=None):
        """Sync wrapper around the async fetch."""
        return asyncio.run(self.fetch_async(url, headers=headers))

    async def fetch_async(self, url, headers=None):
        blocked = self._blocked(url)
        if blocked is not None:
            return blocked
        host = urlsplit(url).hostname.lower()
        request = FetchRequest(url, TIMEOUT_SECONDS, self._headers(headers))
        max_attempts = 1 + MAX_RETRIES
        for attempt in range(1, max_attempts + 1):
            await self._wait(host)
            try:
                response = await self._invoke(request)
            except TimeoutError:
                if attempt == max_attempts:
                    result = FetchResult(
                        False, 'timeout', None, url, b'', self._stamp(), attempt, '', 'timeout',
                    )
                    write_response(self.cache_dir, result)
                    return result
                continue
            except TransportError as exc:
                result = FetchResult(
                    False, 'http_status', None, url, b'', self._stamp(), attempt, '', exc.detail,
                )
                write_response(self.cache_dir, result)
                return result
            body = response.body
            if isinstance(body, str):
                body = body.encode('utf-8')
            if not isinstance(body, bytes):
                body = b''
            origin = response.origin or 'recorded'
            if len(body) > MAX_BODY_BYTES:
                result = FetchResult(
                    False,
                    'body_too_large',
                    response.status,
                    url,
                    body,
                    self._stamp(),
                    attempt,
                    origin,
                    'body_too_large',
                )
                write_response(self.cache_dir, result)
                return result
            if response.status in RETRY_STATUSES and attempt < max_attempts:
                continue
            reason = '' if response.status == 200 else 'http_status'
            result = FetchResult(
                response.status == 200,
                reason,
                response.status,
                url,
                body,
                self._stamp(),
                attempt,
                origin,
                '',
            )
            write_response(self.cache_dir, result)
            return result
        result = FetchResult(
            False, 'timeout', None, url, b'', self._stamp(), max_attempts, '', 'timeout',
        )
        write_response(self.cache_dir, result)
        return result

    def _blocked(self, url):
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        if (
            parsed.scheme != 'https'
            or host not in ALLOWLIST
            or parsed.username is not None
            or parsed.password is not None
        ):
            return FetchResult(
                False,
                'not_allowlisted',
                None,
                url,
                b'',
                self._stamp(),
                0,
                '',
                'not_allowlisted',
            )
        return None

    def _headers(self, headers):
        base = {'User-Agent': 'HuginnMuninn/1.0'}
        if headers:
            pairs = headers.items() if isinstance(headers, dict) else headers
            for key, value in pairs:
                base[str(key)] = str(value)
        return tuple(sorted(base.items()))

    def _stamp(self):
        value = self.retrieved_at
        if callable(value):
            return value()
        if isinstance(value, str) and value.strip() != '':
            return value
        return _utc_now()

    async def _wait(self, host):
        now = self.clock()
        last = self._last.get(host)
        if last is not None and now - last < MIN_INTERVAL_SECONDS:
            await self.sleep(MIN_INTERVAL_SECONDS - (now - last))
            now = self.clock()
        self._last[host] = now

    async def _invoke(self, request):
        outcome = self.transport(request)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return outcome


def live_transport(request):
    """Blocking GET. Call this only from an explicit refresh."""
    import socket
    import urllib.error
    import urllib.request

    class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(_RefuseRedirect)
    outgoing = urllib.request.Request(
        request.url,
        headers=dict(request.headers),
        method='GET',
    )
    try:
        with opener.open(outgoing, timeout=request.timeout) as response:
            return TransportResponse(response.status, response.read(), 'live')
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return TransportResponse(exc.code, payload, 'live')
    except (TimeoutError, socket.timeout):
        raise TimeoutError('timeout')
    except urllib.error.URLError as exc:
        reason = getattr(exc, 'reason', exc)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            raise TimeoutError('timeout')
        raise TransportError(str(reason))
