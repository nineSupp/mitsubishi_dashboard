"""Score item-level forecasts against actuals at several aggregation levels."""
import numpy as np
import pandas as pd

from forecasting.metrics import summarise


def score_levels(panel, n_train, fut_qty, price, label):
    """fut_qty: [items x H] forecast quantity. Returns one row per (level, target)."""
    H = fut_qty.shape[1]
    aq = panel.Q[:, n_train:n_train + H]
    ar = panel.R[:, n_train:n_train + H]
    fr = fut_qty * price[:, None]
    cat = panel.meta['category'].to_numpy()
    rows = []

    def add(level, target, a, f):
        d = summarise(a, f); d.update(Model=label, Level=level, Target=target); rows.append(d)

    add('SKU x month', 'Quantity', aq, fut_qty)
    add('SKU x month', 'Revenue', ar, fr)
    cats = np.unique(cat)
    for target, a, f in (('Quantity', aq, fut_qty), ('Revenue', ar, fr)):
        ca = np.vstack([a[cat == c].sum(0) for c in cats]); cf = np.vstack([f[cat == c].sum(0) for c in cats])
        add('Category x month', target, ca, cf)
        add('Company x month', target, a.sum(0), f.sum(0))
        add('Company x year', target, np.array([a.sum()]), np.array([f.sum()]))
    return rows
