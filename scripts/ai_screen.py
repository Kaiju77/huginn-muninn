#!/usr/bin/env python3
"""Ask GitHub Models to screen today's headlines; write data/news/ai_screen.json.

    python scripts/ai_screen.py

Needs GITHUB_TOKEN with the models:read permission (set in the workflow).
Always writes the status file, with ok=false on any failure, so the brief
can say the AI screen was unavailable.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn.ai_screen import messages, numbered, parse  # noqa: E402
from src.huginn_muninn.catalog import load_catalog  # noqa: E402

NEWS = ROOT / 'data' / 'news' / 'latest.json'
OUT = ROOT / 'data' / 'news' / 'ai_screen.json'
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
ENDPOINT = 'https://models.github.ai/inference/chat/completions'
MODELS = ('openai/gpt-4.1-mini', 'openai/gpt-4o-mini')


def call(model, msgs, token, run=subprocess.run):
    """POST to GitHub Models with curl, exactly as GitHub's quickstart does.

    Python's urllib turns a redirected POST into a GET, which got a bare "OK"
    back; curl keeps the request as documented. The token goes in a temporary
    header file (mode 600), never on the command line.
    """
    body = json.dumps({'model': model, 'messages': msgs, 'temperature': 0,
                       'response_format': {'type': 'json_object'}})
    with tempfile.TemporaryDirectory() as tmp:
        headers = Path(tmp) / 'h'
        headers.write_text(
            f'Authorization: Bearer {token}\n'
            'Accept: application/vnd.github+json\n'
            'X-GitHub-Api-Version: 2022-11-28\n'
            'Content-Type: application/json\n'
            'User-Agent: huginn-muninn-ai-screen\n', encoding='utf-8')
        headers.chmod(0o600)
        data = Path(tmp) / 'd'
        data.write_text(body, encoding='utf-8')
        done = run(['curl', '-sS', '-L', '--max-time', '120', '-X', 'POST',
                    '-H', f'@{headers}', '--data-binary', f'@{data}',
                    '-w', '\n%{http_code}', ENDPOINT],
                   capture_output=True, text=True, timeout=150)
    if done.returncode != 0:
        raise ValueError(f'curl exit {done.returncode}: {done.stderr[:160]}')
    raw, _, status = done.stdout.rpartition('\n')
    if not status.startswith('2'):
        raise ValueError(f'HTTP {status}: {raw[:160]!r}')
    try:
        payload = json.loads(raw.strip().lstrip('\ufeff'))
    except ValueError:
        raise ValueError(f'HTTP {status} non-JSON response: {raw[:160]!r}') from None
    return payload['choices'][0]['message']['content']


def screen(news, token, catalog, call=call):
    fetched = datetime.fromisoformat(news['fetched_at']).astimezone(timezone.utc)
    on = fetched.date()
    items = numbered(news['articles'])
    status = {'date': on.isoformat(), 'ok': False, 'model': '', 'headlines': len(items),
              'candidates': [], 'notes': [], 'rejected': 0, 'error': ''}
    if not items:
        status.update(ok=True, error='no relevant headlines')
        return status
    errors = []
    for model in MODELS:
        for attempt in range(2):
            text = ''
            try:
                text = call(model, messages(items, on), token)
                cands, notes, rejected = parse(text, items, on, catalog)
            except urllib.error.HTTPError as err:
                detail = err.read()[:200].decode('utf-8', 'replace') if err.fp else ''
                errors.append(f'{model}: HTTP {err.code} {detail}'.strip())
                break  # try the next model
            except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError,
                    ValueError) as err:
                # A short start of the model's own reply helps debugging; it never
                # contains the token.
                snippet = (text or '')[:160].replace('\n', ' ')
                errors.append(f'{model}: {type(err).__name__}: {str(err)[:200]} {snippet!r}')
                time.sleep(5)
                continue
            status.update(ok=True, model=model, rejected=rejected, notes=notes,
                          error=' | '.join(errors),
                          candidates=[{**c._asdict(), 'date_public': c.date_public.isoformat(),
                                       'event_type': t} for c, t in cands])
            return status
    status['error'] = ' | '.join(errors)[:1000]
    return status


def main():
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    try:
        news = json.loads(NEWS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        news = None
    if news is None:
        status = {'date': '', 'ok': False, 'error': 'no news file'}
    elif not token:
        status = {'date': '', 'ok': False, 'error': 'GITHUB_TOKEN not set'}
    else:
        status = screen(news, token, load_catalog(EVENTS))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f"AI screen ok={status.get('ok')} candidates={len(status.get('candidates', []))} "
          f"notes={len(status.get('notes', []))} {status.get('error', '')}")
    return 0  # never fails the job; the brief reports the status


if __name__ == '__main__':
    sys.exit(main())
