"""Item x month matrices built from realised (non-Closed) orders on a fiscal-month grid."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from core.data import realised


@dataclass
class Panel:
    items: np.ndarray            # item codes, row order of the matrices
    months: pd.DatetimeIndex     # column order of the matrices
    Q: np.ndarray                # quantity  [items x months]
    R: np.ndarray                # revenue   [items x months]
    meta: pd.DataFrame           # per item: category, production (as recorded), first_sale index

    def col(self, ts):
        return int(self.months.get_loc(pd.Timestamp(ts)))


def build_panel(df, last_month=None):
    r = realised(df)
    if last_month is not None:
        r = r[r['month'] <= pd.Timestamp(last_month)]
    months = pd.date_range(r['month'].min(), r['month'].max(), freq='MS')
    g = r.groupby(['item', 'month'], observed=True)[['qty', 'sales']].sum()
    q = g['qty'].unstack('month').reindex(columns=months).fillna(0.0)
    s = g['sales'].unstack('month').reindex(columns=months).fillna(0.0)
    items = q.index.astype(str).to_numpy()
    last = r.sort_values('date').groupby('item', observed=True).agg(
        category=('category', 'last'), category2=('category2', 'last'), production=('production', 'last'))
    meta = last.reindex(q.index).copy()
    meta.index = items
    meta['production'] = meta['production'].astype(str)
    meta['category'] = meta['category'].astype(str)
    # production flag as recorded in the history file (no look-ahead) where available
    ph = r[r['source'] == 'history'].groupby('item', observed=True)['production_hist'].last().reindex(q.index)
    ph.index = items
    meta['production'] = ph.where(ph.notna(), meta['production']).astype(str)
    Q = q.to_numpy(float)
    meta['first_sale'] = np.where((Q > 0).any(1), (Q > 0).argmax(1), -1)
    return Panel(items, months, Q, s.to_numpy(float), meta)


def outlier_cap(panel, n_train, pct=99.5):
    """Cap on a single item-month quantity, estimated from the training months only."""
    pos = panel.Q[:, :n_train]
    return float(np.percentile(pos[pos > 0], pct))


def cap_outliers(panel, cap):
    """Winsorise quantities at `cap` (revenue is scaled so unit prices are unchanged)."""
    Qc = np.minimum(panel.Q, cap)
    ratio = np.where(panel.Q > 0, Qc / np.where(panel.Q > 0, panel.Q, 1), 1.0)
    return Panel(panel.items, panel.months, Qc, panel.R * ratio, panel.meta)


def truncate(panel, n):
    """The panel as it looked after its first `n` months (nothing later is visible)."""
    sold = panel.Q[:, :n] > 0
    meta = panel.meta.copy()
    meta['first_sale'] = np.where(sold.any(1), sold.argmax(1), -1)
    return Panel(panel.items, panel.months[:n], panel.Q[:, :n], panel.R[:, :n], meta)
