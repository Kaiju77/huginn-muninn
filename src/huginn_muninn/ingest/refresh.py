"""One explicit public refresh. This is not a scheduler.

When the caller passes a transport or explicit_live, the requests are
Norges Bank USD/NOK, Norges Bank EUR/NOK, the verified policy rate
IR/B.KPRA.SD.R, the NOWA rate SHORT_RATES/B.NOWA.ON.R, ECB NOK/EUR,
and then one Statistics Norway cell.
IR/K.POL.NOK returned HTTP 404 and is not requested.
Table 03013 is discontinued through 2025M12 and is not called.
The Statistics Norway request is table 14700, time 2026M07, group 00,
contents KpiIndMnd. No other Statistics Norway URL is requested.
SEC EDGAR is not called. FRED is not allowlisted.
"""

from datetime import date
import asyncio
from typing import NamedTuple

from src.huginn_muninn.ingest.cache import write_refresh
from src.huginn_muninn.ingest.client import Client, FetchResult, live_transport
from src.huginn_muninn.ingest.ecb import fetch_nok_eur
from src.huginn_muninn.ingest.norges import (
    fetch_eur_nok,
    fetch_nowa,
    fetch_policy_rate,
    fetch_usd_nok,
)
from src.huginn_muninn.ingest.ssb import fetch_cpi_total


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
    """Fetch the connected public series for one posted window."""
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
    for fetch in (fetch_usd_nok, fetch_eur_nok, fetch_policy_rate, fetch_nowa, fetch_nok_eur):
        fetched = await fetch(client, start_period, end_period)
        observations.extend(fetched.observations)
        if fetched.error is not None:
            errors.append(fetched.error)
    cpi = await fetch_cpi_total(client)
    observations.extend(cpi.observations)
    if cpi.error is not None:
        errors.append(cpi.error)
    write_refresh(cache_dir, stamp, observations, errors)
    return RefreshResult(tuple(observations), tuple(errors), stamp)
