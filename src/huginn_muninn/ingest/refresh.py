"""One explicit public refresh. This is not a scheduler.

Norges Bank USD/NOK and ECB NOK/EUR are the only requests.
Statistics Norway is not called: a bounded live query was not locked.
SEC EDGAR is not called. FRED is not allowlisted.
The Norges Bank policy-rate series is not requested.
"""

from datetime import date
import asyncio
from typing import NamedTuple

from src.huginn_muninn.ingest.cache import write_refresh
from src.huginn_muninn.ingest.client import Client, FetchResult, live_transport
from src.huginn_muninn.ingest.ecb import fetch_nok_eur
from src.huginn_muninn.ingest.norges import fetch_usd_nok


class RefreshResult(NamedTuple):
    observations: tuple
    errors: tuple
    retrieved_at: str


def _window_error(retrieved_at):
    error = FetchResult(
        False,
        'configuration_required',
        None,
        '',
        b'',
        retrieved_at,
        0,
        '',
        'An explicit start_period and end_period are required.',
    )
    return RefreshResult((), (error,), retrieved_at)


def _dates_ok(start_period, end_period):
    try:
        start = date.fromisoformat(start_period)
        end = date.fromisoformat(end_period)
    except (TypeError, ValueError):
        return False
    return start <= end


def refresh_public(
    cache_dir,
    start_period,
    end_period,
    transport=None,
    explicit_live=False,
    retrieved_at=None,
    clock=None,
    sleep=None,
):
    """Fetch the two connected series for one posted window."""
    return asyncio.run(_refresh_async(
        cache_dir,
        start_period,
        end_period,
        transport,
        explicit_live,
        retrieved_at,
        clock,
        sleep,
    ))


async def _refresh_async(
    cache_dir,
    start_period,
    end_period,
    transport,
    explicit_live,
    retrieved_at,
    clock,
    sleep,
):
    from src.huginn_muninn.ingest.client import _utc_now

    stamp = retrieved_at if isinstance(retrieved_at, str) and retrieved_at.strip() != '' else _utc_now()
    if not _dates_ok(start_period, end_period):
        return _window_error(stamp)
    if transport is None:
        if not explicit_live:
            error = FetchResult(
                False,
                'configuration_required',
                None,
                '',
                b'',
                stamp,
                0,
                '',
                'An explicit live refresh or a transport is required.',
            )
            return RefreshResult((), (error,), stamp)
        transport = live_transport
    client = Client(
        transport,
        cache_dir,
        clock=clock,
        sleep=sleep,
        retrieved_at=stamp,
    )
    observations = []
    errors = []
    norges = await fetch_usd_nok(client, start_period, end_period)
    observations.extend(norges.observations)
    if norges.error is not None:
        errors.append(norges.error)
    ecb = await fetch_nok_eur(client, start_period, end_period)
    observations.extend(ecb.observations)
    if ecb.error is not None:
        errors.append(ecb.error)
    write_refresh(cache_dir, stamp, observations, errors)
    return RefreshResult(tuple(observations), tuple(errors), stamp)
