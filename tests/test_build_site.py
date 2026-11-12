import tempfile
import unittest
from pathlib import Path

from scripts.build_site import PAGES, build


class BuildSiteTest(unittest.TestCase):
    def test_only_listed_reports_are_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports, out = Path(tmp) / 'r', Path(tmp) / 's'
            reports.mkdir()
            (reports / 'latest.md').write_text('# Daily market brief\n', encoding='utf-8')
            (reports / 'secret.md').write_text('private', encoding='utf-8')
            build(out, reports)
            files = sorted(p.name for p in out.iterdir())
            self.assertEqual(files, sorted(['_config.yml'] + [p for _, p, _ in PAGES]))
            index = (out / 'index.md').read_text(encoding='utf-8')
            self.assertIn('# Daily market brief', index)
            self.assertIn('**Daily brief**', index)
            self.assertIn('[Is it right? (backtest)](calibration.html)', index)
            self.assertIn('Not a forecast or advice', index)
            self.assertIn('Not generated yet', (out / 'calibration.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
