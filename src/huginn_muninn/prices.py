"""Load a daily price CSV (date, value) into study.Close rows."""

import csv
from datetime import date
from pathlib import Path

from src.huginn_muninn.study import Close, sorted_closes


def load_closes(path):
    path = Path(path)
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header or len(header) != 2 or header[0] != 'date':
            raise ValueError(f'{path.name}: header must be date,<value column>')
        closes = []
        for line, row in enumerate(reader, start=2):
            if not row:
                continue
            try:
                closes.append(Close(date.fromisoformat(row[0]), float(row[1])))
            except (ValueError, IndexError):
                raise ValueError(f'{path.name} line {line}: bad row {row!r}') from None
    return sorted_closes(closes)
