"""Cached loaders (the only place that mixes Streamlit caching with the data layer)."""
import json
import pandas as pd
import streamlit as st

import config
from core.data import build_dataset

OUTPUT_FILES = {
    'company': 'forecast_company.csv', 'category': 'forecast_category.csv', 'item': 'forecast_item.csv',
    'by_model': 'fy25_company_by_model.csv', 'inventory': 'inventory_profile.csv', 'eval': 'eval_all_folds.csv',
}


def data_files_present():
    from core.data import data_status
    return data_status()['ready']


@st.cache_data(show_spinner="Loading dataset...")
def load_dataset(stamp, include_added=True):
    """The dashboard's data = FY2021-FY2024 history (+ any files added on the 'Add New Data' page).
    The FY2025 orders in TNIC_Data_2025.xlsx are NOT included; they are only used to score the forecast."""
    df, items, _ = build_dataset(include_added=include_added)
    return df, items


@st.cache_data(show_spinner="Loading forecasts...")
def load_outputs(stamp):
    """Returns a dict of DataFrames, or None when the forecast scripts have not been run yet."""
    out = {}
    for key, fname in OUTPUT_FILES.items():
        p = config.OUTPUT_DIR / fname
        if not p.exists():
            return None
        out[key] = pd.read_csv(p)
    for key in ('company', 'category', 'item', 'by_model'):
        out[key]['month'] = pd.to_datetime(out[key]['month'])
    for col in ('first_sale', 'last_sale'):
        out['inventory'][col] = pd.to_datetime(out['inventory'][col], errors='coerce')
    info = config.OUTPUT_DIR / 'run_info.json'
    out['info'] = json.loads(info.read_text()) if info.exists() else {}
    out['updated'] = load_updated()
    return out


def load_updated():
    """Forecast retrained on history + added data (created on the 'Add New Data' page), or None."""
    from forecasting.live import UPDATED_FILES
    paths = {k: config.OUTPUT_DIR / f for k, f in UPDATED_FILES.items()}
    if not all(p.exists() for p in paths.values()):
        return None
    u = {k: pd.read_csv(p) for k, p in paths.items()}
    for k in ('company', 'category'):
        u[k]['month'] = pd.to_datetime(u[k]['month'])
    for col in ('first_sale', 'last_sale'):
        u['inventory'][col] = pd.to_datetime(u['inventory'][col], errors='coerce')
    info = config.OUTPUT_DIR / 'updated_info.json'
    u['info'] = json.loads(info.read_text()) if info.exists() else {}
    return u


def stamps():
    """File modification times, so the caches refresh when data or forecasts change."""
    def m(p):
        return p.stat().st_mtime if p.exists() else 0
    proc = config.DATA_DIR / 'processed'
    data = sum(m(p) for p in (config.find_data_file("history"), config.find_data_file("actuals"),
                              proc / 'item_master.csv', proc / 'customer_master.csv') if p is not None)
    added_dir = config.DATA_DIR / 'added'
    added = [(p.name, m(p)) for p in sorted(added_dir.glob('*.csv'))] if added_dir.exists() else []
    from forecasting.live import UPDATED_FILES
    outs = sum(m(config.OUTPUT_DIR / f) for f in list(OUTPUT_FILES.values()) + list(UPDATED_FILES.values()))
    return (data, tuple(added)), outs
