from decimal import Decimal, getcontext

getcontext().prec = 28

class Portfolio:
    def __init__(self):
        self.assets = {}
        self.currency = 'NOK'
        self.as_of = '2026-10-06'

    def add_asset(self, path, content):
        self.assets[path] = content

    def get_asset(self, path):
        return self.assets.get(path, None)

    def get_total_value(self):
        total_value = Decimal(0)
        for asset in self.assets.values():
            if isinstance(asset, Decimal):
                total_value += asset
        return total_value

    def get_currency(self):
        return self.currency

    def get_as_of(self):
        return self.as_of

    def set_currency(self, currency):
        self.currency = currency

    def set_as_of(self, as_of):
        self.as_of = as_of

    def __str__(self):
        return f'Portfolio(cash={self.get_total_value()}, currency={self.get_currency()}, as_of={self.get_as_of()})'