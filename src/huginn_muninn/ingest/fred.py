"""FRED stays blocked.

api.stlouisfed.org and data.stlouisfed.org are not on the allowlist.
There is no fetch function.
"""

BLOCKED_REASON = 'api_key_and_terms'
HOSTS = ('api.stlouisfed.org', 'data.stlouisfed.org')


def status():
    return {
        'source_id': 'fred',
        'live_fetch': False,
        'blocked_reason': BLOCKED_REASON,
        'allowlisted': False,
    }
