"""Plain data for the results page (no Streamlit here, so it is testable)."""

from src.huginn_muninn.study import event_path, event_return, run_study


def _pct(x):
    return None if x is None else round(x * 100, 1)


def base_rate_rows(results):
    """One dict per horizon: the event figures and the baseline, in percent."""
    rows = []
    for r in results:
        s, b = r.events, r.baseline
        rows.append({
            'horizon (trading days)': r.horizon,
            'events n': s.n,
            'rose': s.rises,
            'share rose %': None if s.too_few else _pct(s.share),
            '95% CI %': None if s.too_few else f'{_pct(s.ci_low)}-{_pct(s.ci_high)}',
            'median %': _pct(s.median),
            'range %': None if s.n == 0 else f'{_pct(s.low)} to {_pct(s.high)}',
            'baseline n': b.n,
            'baseline share rose %': _pct(b.share),
            'baseline 95% CI %': None if b.share is None else f'{_pct(b.ci_low)}-{_pct(b.ci_high)}',
            'baseline median %': _pct(b.median),
            'baseline range %': None if b.n == 0 else f'{_pct(b.low)} to {_pct(b.high)}',
            'skipped': len(r.skipped),
        })
    return rows


def event_rows(catalog_events, closes, horizons, entry):
    """One dict per catalog event: date, title, change per horizon, source."""
    rows = []
    for ce in catalog_events:
        row = {'date': ce.date_public.isoformat(), 'event': ce.title, 'episode': ce.episode}
        for h in horizons:
            result, reason = event_return(closes, ce.to_event(), h, entry)
            row[f'{h}d %'] = None if result is None else _pct(result.change)
        row['source'] = ce.source_url
        rows.append(row)
    return rows


def paths(catalog_events, closes, days, entry):
    """{label: [(day, pct)]} for every event with a valid entry."""
    out = {}
    for ce in catalog_events:
        p = event_path(closes, ce.to_event(), days, entry)
        if p:
            out[f'{ce.date_public.year} {ce.title[:40]}'] = [(d, _pct(c)) for d, c in p]
    return out


def study(catalog_events, closes, entry, era=None):
    return run_study([e.to_event() for e in catalog_events], closes, entry=entry, era=era)
