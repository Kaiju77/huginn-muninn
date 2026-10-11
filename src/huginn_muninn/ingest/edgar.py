"""SEC EDGAR adapter.

A live request waits until a User-Agent contact string is configured.
This module does not invent that contact, and refresh_public does not call it.
Filings are not prices. Fair access remains 10 requests per second and a
declared user agent.
"""

from src.huginn_muninn.ingest.client import FetchResult
from src.huginn_muninn.ingest.norges import AdapterResult


HOST = 'data.sec.gov'
SOURCE_ID = 'sec-edgar-public'


def _missing(url):
    return FetchResult(
        False,
        'configuration_required',
        None,
        url or '',
        b'',
        '',
        0,
        '',
        'A User-Agent contact string is not configured.',
    )


async def fetch_filings(client, user_agent, url):
    """Refuse until a contact string is configured. Filings are not prices."""
    if not isinstance(user_agent, str) or user_agent.strip() == '':
        return AdapterResult((), _missing(url))
    fetched = await client.fetch_async(url, headers={'User-Agent': user_agent})
    if not fetched.ok:
        return AdapterResult((), fetched)
    return AdapterResult((), None)
