import io
import json
import unittest
import urllib.error

from scripts import fetch_news

GOOD = json.dumps({'articles': [{'title': 'Oil up', 'url': 'https://a.example/1',
                                 'domain': 'a.example', 'seendate': '20261113T060000Z'}]}).encode()


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(results):
    calls = []

    def run(target, timeout=None):
        calls.append(target)
        r = results[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return Resp(r)
    return run, calls


class RetryTest(unittest.TestCase):
    def test_rate_limit_then_success(self):
        err = urllib.error.HTTPError('https://x/?secret', 429, 'Too Many', {}, None)
        run, calls = opener([err, b'Please limit requests to one every 5 seconds', GOOD])
        slept = []
        got = fetch_news.get('u', opener=run, sleep=slept.append)
        self.assertEqual(got[0]['title'], 'Oil up')
        self.assertEqual(len(calls), 3)
        self.assertEqual(slept, list(fetch_news.WAITS[:2]))

    def test_gives_up_after_all_waits(self):
        err = urllib.error.HTTPError('https://x/?secret', 429, 'Too Many', {}, None)
        run, calls = opener([err] * 4)
        with self.assertRaises(urllib.error.HTTPError):
            fetch_news.get('u', opener=run, sleep=lambda s: None)
        self.assertEqual(len(calls), len(fetch_news.WAITS) + 1)

    def test_describe_has_status_but_no_url(self):
        err = urllib.error.HTTPError('https://x/?secret', 429, 'Too Many', {}, None)
        self.assertEqual(fetch_news.describe(err), 'HTTPError 429')
        self.assertEqual(fetch_news.describe(ValueError('https://x/?secret')), 'ValueError')


if __name__ == '__main__':
    unittest.main()
