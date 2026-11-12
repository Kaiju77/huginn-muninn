#!/usr/bin/env python3
"""Ask an AI model to screen today's headlines; write data/news/ai_screen.json.

    python scripts/ai_screen.py

Providers, tried in order, each only if its key is set:
  1. Groq (free plan): GROQ_API_KEY, a repository secret.
  2. GitHub Models: GITHUB_TOKEN with models:read (not available on Kai's
     account as of 2026-11-12; kept in case GitHub enables it).
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
from src.huginn_muninn.daily import parse_fetched  # noqa: E402

NEWS = ROOT / 'data' / 'news' / 'latest.json'
OUT = ROOT / 'data' / 'news' / 'ai_screen.json'
EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'
ENDPOINT = 'https://models.github.ai/inference/chat/completions'
MODELS = ('openai/gpt-4.1-mini', 'openai/gpt-4o-mini')
GROQ_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODELS = ('openai/gpt-oss-120b', 'llama-3.1-8b-instant')
GITHUB_HEADERS = ('Accept: application/vnd.github+json\n'
                  'X-GitHub-Api-Version: 2022-11-28\n')


def call(model, msgs, token, run=subprocess.run, endpoint=ENDPOINT,
         extra_headers=GITHUB_HEADERS, json_mode=True):
    """POST to GitHub Models with curl, exactly as GitHub's quickstart does.

    Python's urllib turns a redirected POST into a GET, which got a bare "OK"
    back; curl keeps the request as documented. The token goes in a temporary
    header file (mode 600), never on the command line.
    """
    request = {'model': model, 'messages': msgs, 'temperature': 0}
    if json_mode:
        request['response_format'] = {'type': 'json_object'}
    body = json.dumps(request)
    with tempfile.TemporaryDirectory() as tmp:
        headers = Path(tmp) / 'h'
        headers.write_text(
            f'Authorization: Bearer {token}\n'
            + extra_headers +
            'Content-Type: application/json\n'
            'User-Agent: huginn-muninn-ai-screen\n', encoding='utf-8')
        headers.chmod(0o600)
        data = Path(tmp) / 'd'
        data.write_text(body, encoding='utf-8')
        done = run(['curl', '-sS', '-L', '--max-time', '120', '-X', 'POST',
                    '-H', f'@{headers}', '--data-binary', f'@{data}',
                    '-w', '\n%{http_code}', endpoint],
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


def groq_call(model, msgs, token, run=subprocess.run):
    # The parser accepts plain or fenced JSON, so JSON mode is not required.
    return call(model, msgs, token, run=run, endpoint=GROQ_ENDPOINT, extra_headers='',
                json_mode=False)


def providers(env):
    """[(name, models, token, call)] for every provider whose key is set."""
    out = []
    if env.get('GROQ_API_KEY', '').strip():
        out.append(('groq', GROQ_MODELS, env['GROQ_API_KEY'].strip(), groq_call))
    if env.get('GITHUB_TOKEN', '').strip():
        out.append(('github-models', MODELS, env['GITHUB_TOKEN'].strip(), call))
    return out


def screen_all(news, provider_list, catalog):
    """Try each provider until one succeeds; keep every error."""
    errors, status = [], None
    for name, models, token, fn in provider_list:
        status = screen(news, token, catalog, call=fn, models=models)
        if status['ok']:
            status['provider'] = name
            if errors:
                status['error'] = ' | '.join(errors + ([status['error']] if status['error'] else []))
            return status
        errors.append(f'{name}: {status["error"]}')
    if status is None:
        return {'date': '', 'ok': False, 'error': 'no AI provider key set'}
    status['error'] = ' || '.join(errors)[:1500]
    return status


def screen(news, token, catalog, call=call, models=MODELS):
    fetched = parse_fetched(news['fetched_at'])
    on = fetched.date()
    items = numbered(news['articles'], fetched)
    status = {'date': on.isoformat(), 'ok': False, 'model': '', 'headlines': len(items),
              'candidates': [], 'notes': [], 'rejected': 0, 'error': ''}
    if not items:
        status.update(ok=True, error='no relevant headlines')
        return status
    errors = []
    for model in models:
        for attempt in range(2):
            text = ''
            try:
                text = call(model, messages(items, on), token)
                cands, notes, rejected = parse(text, items, on, catalog)
            except urllib.error.HTTPError as err:
                detail = err.read()[:200].decode('utf-8', 'replace') if err.fp else ''
                errors.append(f'{model}: HTTP {err.code} {detail}'.strip())
                break  # try the next model
            except (urllib.error.URLError, TimeoutError, subprocess.TimeoutExpired, OSError,
                    KeyError, IndexError, TypeError, ValueError) as err:
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
    try:
        news = json.loads(NEWS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        news = None
    if news is None:
        status = {'date': '', 'ok': False, 'error': 'no news file'}
    else:
        try:
            status = screen_all(news, providers(os.environ), load_catalog(EVENTS))
        except Exception as err:  # never let the AI step break the daily job
            status = {'date': '', 'ok': False, 'error': f'unexpected {type(err).__name__}'}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f"AI screen ok={status.get('ok')} provider={status.get('provider', '')} "
          f"candidates={len(status.get('candidates', []))} "
          f"notes={len(status.get('notes', []))} {status.get('error', '')}")
    return 0  # never fails the job; the brief reports the status


if __name__ == '__main__':
    sys.exit(main())
