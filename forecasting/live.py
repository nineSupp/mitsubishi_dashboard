"""Retrain the forecast on everything the dashboard has (history + data added by the user)."""
import json
from datetime import datetime
import pandas as pd

import config
from core.watchdog import busy
from forecasting.panel import build_panel, truncate
from forecasting.pipeline import official_forecast, inventory_profile

UPDATED_FILES = {'company': 'forecast_updated_company.csv', 'category': 'forecast_updated_category.csv',
                 'inventory': 'inventory_updated.csv'}
MIN_MONTHS = 36


def train_updated(df, out_dir=None):
    with busy():                      # keep the dashboard alive while training
        return _train_updated(df, out_dir)


def _train_updated(df, out_dir=None):
    """df: dashboard dataset including added data. Forecasts the 12 months after its last COMPLETE month."""
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(exist_ok=True)
    panel = build_panel(df)
    n, notes = len(panel.months), []
    if not df['date'].max().is_month_end:
        n -= 1
        notes.append(f"{panel.months[-1]:%b %Y} is incomplete, so it was left out of training.")
    if n < MIN_MONTHS:
        raise ValueError(f"Need at least {MIN_MONTHS} complete months of data, found {n}.")
    tp = truncate(panel, n)
    fc = official_forecast(tp, n)
    prof = inventory_profile(tp, fc['item'])
    fc['company'].to_csv(out_dir / UPDATED_FILES['company'], index=False)
    fc['category'].to_csv(out_dir / UPDATED_FILES['category'], index=False)
    prof.to_csv(out_dir / UPDATED_FILES['inventory'], index=False, float_format='%.4f')
    info = dict(updated=f"{datetime.now():%Y-%m-%d %H:%M}", trained_through=f"{tp.months[-1]:%Y-%m}",
                forecast_from=f"{fc['company']['month'].min():%Y-%m}", forecast_to=f"{fc['company']['month'].max():%Y-%m}",
                months_used=n, order_lines=int(len(df)), notes=notes)
    (out_dir / 'updated_info.json').write_text(json.dumps(info, indent=2))
    return dict(company=fc['company'], category=fc['category'], inventory=prof, info=info)
