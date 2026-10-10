#!/usr/bin/env python3
"""Serve the synthetic paper ledger on 127.0.0.1.

The process refuses any bind address other than loopback. It does not
authenticate, because the ledger is synthetic and the socket is local.
"""

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.huginn_muninn.prototype import dispatch, open_state


def resolve_bind(argv):
    """Return (host, port). Default is 127.0.0.1:8765.

    localhost is normalized to 127.0.0.1. Any other non-loopback address
    raises SystemExit before a socket is opened.
    """
    host = '127.0.0.1'
    port = 8765
    args = list(argv[1:])
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--port':
            if index + 1 >= len(args):
                raise SystemExit('missing port')
            port = int(args[index + 1])
            index += 2
            continue
        if arg == '--bind':
            if index + 1 >= len(args):
                raise SystemExit('refusing non-loopback bind')
            host = args[index + 1]
            index += 2
            continue
        if arg.isdigit():
            port = int(arg)
            index += 1
            continue
        host = arg
        index += 1
    if host == 'localhost':
        host = '127.0.0.1'
    if host not in {'127.0.0.1', '::1'}:
        raise SystemExit('refusing non-loopback bind')
    return host, port


class PrototypeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._serve('GET', {})

    def do_POST(self):
        length_header = self.headers.get('Content-Length', '0') or '0'
        try:
            length = int(length_header)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b''
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            self._write_plain(400, 'The form body must be UTF-8.')
            return
        form = parse_qs(text, keep_blank_values=True)
        self._serve('POST', form)

    def _serve(self, method, form):
        response = dispatch(self.server.prototype_state, method, self.path, form)
        payload = response.body.encode('utf-8')
        self.send_response(response.status)
        self.send_header('Content-Type', response.content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _write_plain(self, status, message):
        payload = message.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main(argv):
    host, port = resolve_bind(argv)
    server = HTTPServer((host, port), PrototypeHandler)
    server.prototype_state = open_state(_ROOT)
    shown = f'[{host}]' if ':' in host else host
    print(f'http://{shown}:{port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main(sys.argv)
