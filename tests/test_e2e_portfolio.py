import unittest

from scripts.e2e_portfolio import run


class EnteredPortfolioEndToEndTest(unittest.TestCase):
    def test_every_step_passes_over_http(self):
        results = run(verbose=False)
        self.assertGreater(len(results), 5)
        failed = [(step, detail) for step, ok, detail in results if not ok]
        self.assertEqual(failed, [])


if __name__ == '__main__':
    unittest.main()
