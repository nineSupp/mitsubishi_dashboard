"""Everything a view needs, bundled once per run."""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd


@dataclass
class AppContext:
    df_all: pd.DataFrame            # every order line (history + FY2025 actuals)
    df_nd: pd.DataFrame             # all sidebar filters EXCEPT the date range
    df_f: pd.DataFrame              # all sidebar filters
    df_prev: pd.DataFrame | None    # previous period of equal length (for % badges)
    f_start: pd.Timestamp
    f_end: pd.Timestamp
    data_min: pd.Timestamp
    data_max: pd.Timestamp
    all_months: pd.DatetimeIndex
    n_months: int
    items_master: pd.DataFrame
    outputs: dict | None            # forecast artefacts (None if scripts.train_forecasts has not been run)
    filters: dict = field(default_factory=dict)


def kpis(d):
    rev, orders, gross = d['sales'].sum(), d['order'].nunique(), d['gross'].sum()
    return dict(revenue=rev, orders=orders, units=d['qty'].sum(), customers=d['customer'].nunique(),
                aov=rev / orders if orders else np.nan, disc=d['discount'].sum() / gross if gross else np.nan)
