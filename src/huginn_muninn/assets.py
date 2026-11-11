"""The price series the study knows about. One place to add an asset."""

from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent.parent
PRICES = ROOT / 'data' / 'prices'


class Asset(NamedTuple):
    asset_id: str
    label: str
    unit: str
    source: str        # 'eia' or 'norges-bank'
    route: str         # EIA route or Norges Bank series path
    series: str        # EIA series id ('' for Norges Bank)
    allow_nonpositive: bool = False

    @property
    def csv_path(self) -> Path:
        return PRICES / f'{self.asset_id}.csv'


ASSETS = (
    Asset('brent', 'Brent', 'USD/barrel', 'eia', 'petroleum/pri/spt', 'RBRTE'),
    # WTI settled at -36.98 on 2020-04-20. Kept as published; the study skips
    # any event whose entry close is not positive.
    Asset('wti', 'WTI', 'USD/barrel', 'eia', 'petroleum/pri/spt', 'RWTC',
          allow_nonpositive=True),
    Asset('henry_hub', 'Henry Hub gas', 'USD/MMBtu', 'eia', 'natural-gas/pri/fut', 'RNGWHHD'),
    Asset('usd_nok', 'USD/NOK', 'NOK per USD', 'norges-bank', 'EXR/B.USD.NOK.SP', ''),
)

BY_ID = {a.asset_id: a for a in ASSETS}
