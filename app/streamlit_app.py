"""Results page: historical base rates after Middle East conflicts.

    pip install -r requirements-app.txt
    streamlit run app/streamlit_app.py
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huginn_muninn import report  # noqa: E402
from src.huginn_muninn.assets import ASSETS  # noqa: E402
from src.huginn_muninn.catalog import first_per_episode, load_catalog  # noqa: E402
from src.huginn_muninn.prices import load_closes  # noqa: E402
from src.huginn_muninn.study import AFTER_NEWS, BEFORE_NEWS, DEFAULT_HORIZONS  # noqa: E402

EVENTS = ROOT / 'data' / 'events' / 'mideast-conflict.csv'

st.set_page_config(page_title='Huginn & Muninn: event base rates', layout='wide')
st.title('What happened after Middle East conflicts?')
st.caption('Historical base rates, not a forecast or advice. You make the decisions.')

available = [a for a in ASSETS if a.csv_path.exists()]
if not available:
    st.error('No price files yet. Run the fetch-prices workflow first.')
    st.stop()

with st.sidebar:
    asset = st.selectbox('Asset', available, format_func=lambda a: f'{a.label} ({a.unit})')
    entry_label = st.radio(
        'Start price',
        ['After the news (first close you could act on)', 'Before the news (includes the first jump)'],
    )
    entry = AFTER_NEWS if entry_label.startswith('After') else BEFORE_NEWS
    one_per_episode = st.checkbox('One event per crisis (independent sample)', value=True)
    use_era = st.checkbox('Limit to a period')
    era = None
    if use_era:
        start, end = st.slider('Period', 1987, date.today().year, (2000, date.today().year))
        era = (date(start, 1, 1), date(end, 12, 31))
    path_days = st.slider('Chart length (trading days)', 5, 120, 60)


@st.cache_data
def _load(path_str, mtime):
    return load_closes(path_str)


closes = _load(str(asset.csv_path), asset.csv_path.stat().st_mtime)
catalog = load_catalog(EVENTS)
chosen = first_per_episode(catalog) if one_per_episode else catalog
if era:
    chosen = [e for e in chosen if era[0] <= e.date_public <= era[1]]

st.write(f'**{len(chosen)} events** ({len(catalog)} in catalog). '
         f'{asset.label} prices {closes[0].on} to {closes[-1].on}.')

results = report.study(chosen, closes, entry, era)
st.subheader('Base rates')
st.dataframe(pd.DataFrame(report.base_rate_rows(results)), hide_index=True, width='stretch')
st.caption('Rose = change above 0. CI = Wilson 95% interval. Fewer than 8 events: no percentage. '
           'Baseline = every non-overlapping window of the same length in the same period.')

st.subheader(f'{asset.label} after each event (% from the start price)')
paths = report.paths(chosen, closes, path_days, entry)
if paths:
    frame = pd.DataFrame({k: dict(v) for k, v in paths.items()})
    frame['MEDIAN'] = frame.median(axis=1)
    st.line_chart(frame)
else:
    st.info('No event has price data for this selection.')

st.subheader('Events')
st.dataframe(
    pd.DataFrame(report.event_rows(chosen, closes, DEFAULT_HORIZONS, entry)),
    hide_index=True, width='stretch',
    column_config={'source': st.column_config.LinkColumn('source')},
)
st.caption('The event list was picked by hand and may overstate effects. See data/events/README.md.')
