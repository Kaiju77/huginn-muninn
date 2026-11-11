# End-to-end check: entered portfolio

One core workflow, run over real HTTP against the prototype server, with synthetic data only.

## Steps

1. Empty book loads (`GET /portfolio`).
2. Add account, then a NOK fund (`POST /portfolio`).
3. Contribute 1000 NOK on 2026-05-01.
4. Buy 10 units for 500 NOK with a fee of 10 NOK on 2026-05-02.
5. Value on 2026-05-03 with no price: the price stays unknown and allocation is incomplete.
6. Record prices of 50 (2026-05-02) and 60 (2026-05-03) (`POST /portfolio/valuation`).
7. Value on 2026-05-03: known NOK subtotal 1090 (490 cash + 10 x 60).
8. Performance from 2026-05-01 to 2026-05-03: start 1000, end 1090, fees 10, price change 100.
9. The store went only to a temp directory, and `fixtures/synthetic_portfolio.json` is unchanged.

The server binds `127.0.0.1` on an ephemeral port. Nothing is fetched, and nothing in `var/` is written.

## Commands (from the checkout root)

Run the workflow. It prints PASS/FAIL per step and exits 1 on any failure:

    python scripts/e2e_portfolio.py

Run the same check as a unit test:

    python -m unittest tests.test_e2e_portfolio -v

Run the full suite (196 tests on 2026-11-11):

    python -m unittest discover -s tests

Open the pages by hand (uses `var/`, not the temp store):

    python scripts/serve_prototype.py
    # then open http://127.0.0.1:8765/portfolio
