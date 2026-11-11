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
         'OR syria OR hormuz OR "red sea" OR qatar OR uae OR libya) sourcelang:english')


def url(query=QUERY, timespan='1d', maxrecords=75):
    return ENDPOINT + '?' + urllib.parse.urlencode({
        'query': query, 'mode': 'ArtList', 'format': 'json',
        'timespan': timespan, 'maxrecords': str(maxrecords), 'sort': 'DateDesc',
    })


def parse(body):
    text = body.decode('utf-8', errors='replace').strip()
    if not text:
        return []
    data = json.loads(text)
    articles = data.get('articles', [])
    if not isinstance(articles, list):
        raise ValueError('unexpected GDELT response')
    return [{k: a.get(k, '') for k in ('title', 'url', 'domain', 'seendate', 'sourcecountry')}
            for a in articles if isinstance(a, dict)]


def get(target, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(target, timeout=60) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))  # GDELT asks for a pause between calls


def main():
    try:
        articles = parse(get(url()))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as err:
        print(f'news not written: {type(err).__name__}', file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'query': QUERY, 'articles': articles}
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'{len(articles)} articles')
    return 0


if __name__ == '__main__':
    sys.exit(main())
