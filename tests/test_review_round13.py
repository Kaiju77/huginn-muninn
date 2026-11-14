"""Review round 13: nothing in a headline may run on the public page."""
import http.client
import tempfile
import unittest
import urllib.error
from pathlib import Path

from scripts import fetch_news
from scripts.build_site import build, no_liquid
from scripts.compare_catalogs import md as compare_md
from src.huginn_muninn.mdsafe import md, url
from tests.test_fetch_news_retry import GOOD, opener

EVIL = ('Oil *x*{: onmouseover="alert(1)"} <img src=x onerror=alert(2)> '
        '{{ site.github.owner_name }} {% include nope.html %} [a](javascript:1) `c` | t\n\n## H')


class EscapeTest(unittest.TestCase):
    def test_md_neutralises_html_kramdown_and_liquid(self):
        for out in (md(EVIL), compare_md(EVIL)):
            for bad in ('<', '>', '{', '}', '%', '|', '[', ']', '`', '\n', '\\'):
                self.assertNotIn(bad, out)
            self.assertIn('&lt;img', out)

    def test_url_only_http_and_fully_encoded(self):
        self.assertEqual(url('javascript:alert(1)'), '')
        out = url('https://a.example/x y)"{{b}}<c>?q=1&r=2#f')
        self.assertEqual(out, 'https://a.example/x%20y%29%22%7B%7Bb%7D%7D%3Cc%3E?q=1&r=2#f')

    def test_daily_report_uses_the_shared_escaper(self):
        from scripts import daily_report
        self.assertIs(daily_report.md, md)
        self.assertIs(daily_report.url, url)
        src = Path(daily_report.__file__).read_text(encoding='utf-8')
        self.assertIn('md(event.title)', src)
        self.assertIn('url(event.source_url)', src)

    def test_site_body_is_liquid_raw(self):
        body = no_liquid('x {% endraw %} {%- endraw -%} {% include a %}')
        self.assertTrue(body.startswith('{% raw %}'))
        self.assertEqual(body.count('endraw'), 1)
        with tempfile.TemporaryDirectory() as tmp:
            reports, out = Path(tmp) / 'r', Path(tmp) / 's'
            reports.mkdir()
            (reports / 'latest.md').write_text('{{ site.x }}', encoding='utf-8')
            build(out, reports)
            text = (out / 'index.md').read_text(encoding='utf-8')
            self.assertLess(text.index('{% raw %}'), text.index('{{ site.x }}'))
            self.assertLess(text.index('{{ site.x }}'), text.index('{% endraw %}'))


class FetchTest(unittest.TestCase):
    def test_low_level_network_errors_are_retried(self):
        errs = [http.client.IncompleteRead(b''), ConnectionResetError(),
                http.client.RemoteDisconnected('x'), GOOD]
        run, calls = opener(errs)
        self.assertEqual(len(fetch_news.get('u', opener=run, sleep=lambda s: None)), 1)
        self.assertEqual(len(calls), 4)

    def test_permanent_http_error_is_not_retried(self):
        run, calls = opener([urllib.error.HTTPError('u', 404, 'x', {}, None)] * 4)
        with self.assertRaises(urllib.error.HTTPError):
            fetch_news.get('u', opener=run, sleep=lambda s: self.fail('slept'))
        self.assertEqual(len(calls), 1)

    def test_main_reports_instead_of_traceback(self):
        old = fetch_news.get
        fetch_news.get = lambda *_a, **_k: (_ for _ in ()).throw(http.client.IncompleteRead(b''))
        try:
            self.assertEqual(fetch_news.main(), 1)
        finally:
            fetch_news.get = old


if __name__ == '__main__':
    unittest.main()
