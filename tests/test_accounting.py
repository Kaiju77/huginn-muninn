from src.huginn_muninn.accounting import Portfolio, Decimal

def test_portfolio_initialization():
    portfolio = Portfolio()
    assert portfolio.get_total_value() == Decimal(0)
    assert portfolio.get_currency() == 'NOK'
    assert portfolio.get_as_of() == '2026-10-06'

def test_portfolio_add_asset():
    portfolio = Portfolio()
    portfolio.add_asset('cash', Decimal(1000))
    assert portfolio.get_total_value() == Decimal(1000)

def test_portfolio_get_asset():
    portfolio = Portfolio()
    portfolio.add_asset('cash', Decimal(1000))
    assert portfolio.get_asset('cash') == Decimal(1000)

def test_portfolio_set_currency():
    portfolio = Portfolio()
    portfolio.set_currency('USD')
    assert portfolio.get_currency() == 'USD'

def test_portfolio_set_as_of():
    portfolio = Portfolio()
    portfolio.set_as_of('2026-10-07')
    assert portfolio.get_as_of() == '2026-10-07'