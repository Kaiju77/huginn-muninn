#!/usr/bin/env python3
"""Fetch the last day's oil and Middle East headlines from the GDELT DOC API.

    python scripts/fetch_news.py            # writes data/news/latest.json

No key needed. On failure the old file is kept and the exit code is 1;
the report then says news is unavailable.
"""

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'news' / 'latest.json'
ENDPOINT = 'https://api.gdeltproject.org/api/v2/doc/doc'
QUERY = ('(oil OR crude OR brent OR opec OR "natural gas" OR lng) '
         '(iran OR israel OR saudi OR iraq OR yemen OR houthi OR gaza OR lebanon '
         'OR syria OR hormuz OR "red sea" OR qatar OR uae OR libya '
         'OR norway OR equinor OR "north sea") sourcelang:english')


def url(query=QUERY, timespan='1d', maxrecords=75):
    return ENDPOINT + '?' + urllib.parse.urlencode({
        'query': query, 'mode': 'ArtList', 'format': 'json',
        'timespan': timespan, 'maxrecords': str(maxrecords), 'sort': 'DateDesc',
    })


def parse(body):
    """Articles from a GDELT ArtList response. An empty body, an object without
    an ``articles`` list, or an error object is a failure, not "no news": the
    query is broad enough that a real day always has matches."""
    text = body.decode('utf-8', errors='replace').strip()
    if not text:
        raise ValueError('empty GDELT response')
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get('articles'), list):
        raise ValueError('GDELT response has no articles list')
    keep = [{k: str(a.get(k) or '') for k in ('title', 'url', 'domain', 'seendate',
                                              'sourcecountry')}
            for a in data['articles'] if isinstance(a, dict)]
    keep = [a for a in keep if a['title'].strip() and a['url'].startswith('http')]
    if not keep:
        raise ValueError('GDELT returned no usable articles')
    return keep


WAITS = (20, 60, 150)   # seconds; GDELT rate-limits shared runner addresses (HTTP 429)


def get(target, waits=WAITS, opener=urllib.request.urlopen, sleep=time.sleep):
    """The parsed articles. A failed call, a rate-limit page or an unusable body
    is retried after each wait in ``waits``; the last error is raised."""
    for attempt in range(len(waits) + 1):
        try:
            with opener(target, timeout=60) as resp:
                return parse(resp.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            if attempt == len(waits):
                raise
            print(f'GDELT attempt {attempt + 1} failed: {describe(err)}; retrying',
                  file=sys.stderr)
            sleep(waits[attempt])


def describe(err):
    """Error class plus the HTTP status. Never the URL or the body."""
    code = getattr(err, 'code', None)
    return f'{type(err).__name__} {code}' if isinstance(code, int) else type(err).__name__


def main():
    try:
        articles = get(url())
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        print(f'news not written: {describe(err)}', file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'query': QUERY, 'articles': articles}
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'{len(articles)} articles')
    return 0


if __name__ == '__main__':
    sys.exit(main())
