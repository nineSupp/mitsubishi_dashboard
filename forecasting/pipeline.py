"""Official forecasts shown in the dashboard.

Chosen by the rolling backtest (see outputs/eval_all_folds.csv):
  * company monthly revenue : Gradient Boosting on lags + seasonality (the original dashboard model)
  * category / item level   : company forecast allocated by each item's recent sales mix (top-down)
"""
import numpy as np
import pandas as pd

from forecasting import item_model as im
import config
from forecasting.panel import outlier_cap, cap_outliers, truncate
from forecasting.series_models import forecast_with_range

COMPANY_MODEL_KEY = 'gbm'


MIX_KINDS = {'flat': None, 'random_forest': 'rf', 'lightgbm': 'lgbm', 'xgboost': 'xgb', 'hurdle': 'hurdle'}


def _mix_quantities(pc, ctx, n_train, horizon, mix):
    """Item-level unit forecast used ONLY for the mix across items. Returns (qty [items x horizon], mix actually used)."""
    kind = MIX_KINDS.get(mix)
    if kind is None or kind not in im.available_kinds():
        return im.baseline_forecasts(pc, ctx, n_train, horizon)['Flat 12-month average'], 'flat'
    X, y = im.training_set(pc, ctx, n_train)
    model = im.ItemDemandModel(kind, n_estimators=100).fit(X, y)
    return im.recursive_forecast(model, pc, ctx, n_train, horizon)[0], mix


def _allocate(panel, n_train, horizon, mix='flat'):
    """Company revenue (Gradient Boosting) split across items by the chosen mix. Uses columns < n_train only."""
    cap = outlier_cap(panel, n_train)
    pc = cap_outliers(panel, cap)
    ctx = im.Context(pc, n_train)
    price = im._last_price(pc, n_train)
    fc, lo, hi = forecast_with_range(panel.R.sum(0)[:n_train], panel.months[:n_train], horizon, COMPANY_MODEL_KEY)
    qty, used = _mix_quantities(pc, ctx, n_train, horizon, mix)
    rev = qty * price[:, None]
    scale = np.where(rev.sum(0) > 0, fc / np.where(rev.sum(0) > 0, rev.sum(0), 1), 1.0)
    item_qty = qty * scale[None, :]
    return dict(cap=cap, pc=pc, price=price, fc=fc, lo=lo, hi=hi, item_qty=item_qty, item_rev=item_qty * price[:, None], mix=used)


def _category_ratios(panel, n_train, horizon, q=(0.10, 0.90), min_points=8):
    """Empirical forecast-error ratios (actual / forecast) per category from the TWO years before the forecast origin,
    each forecast made only from earlier months. Gives the low / high band for category forecasts."""
    pn = truncate(panel, n_train)
    cats = pn.meta['category'].to_numpy()
    pooled, per = [], {}
    for o in (n_train - 2 * horizon, n_train - horizon):
        if o < 24:
            continue
        al = _allocate(pn, o, horizon, 'flat')
        for c in np.unique(cats):
            m = cats == c
            f = al['item_rev'][m].sum(0)
            a = pn.R[m, o:o + horizon].sum(0)
            r = a[f > 0] / f[f > 0]
            per.setdefault(c, []).extend(r.tolist())
            pooled.extend(r.tolist())
    if len(pooled) < min_points:
        return None
    pq = np.quantile(pooled, q)
    out = {}
    for c in np.unique(cats):
        r = np.asarray(per.get(c, []))
        lo_r, hi_r = np.quantile(r, q) if len(r) >= min_points else pq
        out[c] = (min(lo_r, 0.95), max(hi_r, 1.05))
    return out


def _item_ratios(pc, n_train, window=24, q=(0.10, 0.90)):
    """Typical month-to-month swing of each item (10th / 90th percentile of its monthly units relative to its own average)."""
    w = pc.Q[:, max(n_train - window, 0):n_train]
    mean = w.mean(1)
    ok = mean > 0
    r = np.where(ok[:, None], w / np.where(ok, mean, 1)[:, None], 1.0)
    lo_r, hi_r = np.quantile(r, q[0], axis=1), np.quantile(r, q[1], axis=1)
    return np.minimum(lo_r, 1.0), np.maximum(hi_r, 1.0)


def official_forecast(panel, n_train, horizon=12, mix=None):
    """Forecast `horizon` months after column n_train-1 using only columns < n_train.
    Returns company / category / item tables, each with a low-high range (~80%), and attaches the real
    values when those months exist in the panel (backtest). `mix` defaults to config.ITEM_MIX_MODEL."""
    mix = mix or config.ITEM_MIX_MODEL
    al = _allocate(panel, n_train, horizon, mix)
    fut = pd.date_range(panel.months[n_train - 1] + pd.DateOffset(months=1), periods=horizon, freq='MS')
    item_qty, item_rev, fc = al['item_qty'], al['item_rev'], al['fc']

    have_actual = panel.Q.shape[1] >= n_train + horizon
    aq = panel.Q[:, n_train:n_train + horizon] if have_actual else np.full_like(item_qty, np.nan)
    ar = panel.R[:, n_train:n_train + horizon] if have_actual else np.full_like(item_qty, np.nan)
    cats = panel.meta['category'].to_numpy()

    company = pd.DataFrame({'month': fut, 'forecast': fc, 'lo': al['lo'], 'hi': al['hi'],
                            'actual': ar.sum(0) if have_actual else np.nan,
                            'forecast_qty': item_qty.sum(0), 'actual_qty': aq.sum(0) if have_actual else np.nan})

    ratios = _category_ratios(panel, n_train, horizon)
    comp_lo, comp_hi = np.divide(al['lo'], fc, out=np.ones_like(fc), where=fc > 0), np.divide(al['hi'], fc, out=np.ones_like(fc), where=fc > 0)
    rows = []
    for c in np.unique(cats):
        m = cats == c
        for k, ts in enumerate(fut):
            f = item_rev[m, k].sum()
            lo_r, hi_r = ratios[c] if ratios else (comp_lo[k], comp_hi[k])
            rows.append((ts, c, f, item_qty[m, k].sum(), ar[m, k].sum() if have_actual else np.nan,
                         aq[m, k].sum() if have_actual else np.nan, f * lo_r, f * hi_r))
    category = pd.DataFrame(rows, columns=['month', 'category', 'forecast', 'forecast_qty', 'actual', 'actual_qty', 'lo', 'hi'])

    lo_i, hi_i = _item_ratios(al['pc'], n_train)
    keep = (item_qty.sum(1) > 1e-6) | (np.nan_to_num(aq).sum(1) > 0)
    idx = np.where(keep)[0]
    f_rev, f_qty = item_rev[idx].ravel(), item_qty[idx].ravel()
    lo_r, hi_r = np.repeat(lo_i[idx], horizon), np.repeat(hi_i[idx], horizon)
    item = pd.DataFrame({
        'item': np.repeat(panel.items[idx], horizon), 'category': np.repeat(cats[idx], horizon),
        'month': np.tile(fut, len(idx)),
        'forecast_qty': f_qty, 'forecast': f_rev, 'lo': f_rev * lo_r, 'hi': f_rev * hi_r,
        'lo_qty': f_qty * lo_r, 'hi_qty': f_qty * hi_r,
        'actual_qty': aq[idx].ravel(), 'actual': ar[idx].ravel()})
    return dict(company=company, category=category, item=item, cap=al['cap'], price=al['price'], mix=al['mix'])


def inventory_profile(panel, outlook_item, window=12, cap_pct=99.5):
    """Demand statistics per item from the latest `window` months + ABC/XYZ classes and status flags.
    `panel` must end at the forecast origin (Mar 2025): nothing from FY2025 is used.
    Quantities are winsorised so a single bulk order does not dominate the variability estimate."""
    n = panel.Q.shape[1]
    cap = float(np.percentile(panel.Q[panel.Q > 0], cap_pct))
    Qc = np.minimum(panel.Q, cap)
    w = Qc[:, n - window:]
    rev12 = panel.R[:, n - window:].sum(1)
    mean_q, std_q = w.mean(1), w.std(1)
    active12 = (w > 0).sum(1)
    sold = panel.Q > 0
    last_idx = np.where(sold.any(1), n - 1 - sold[:, ::-1].argmax(1), -1)
    first_idx = np.where(sold.any(1), sold.argmax(1), -1)
    since_last = np.where(last_idx >= 0, n - 1 - last_idx, 99)
    q12 = panel.Q[:, n - window:].sum(1)
    price = np.where(q12 > 0, rev12 / np.where(q12 > 0, q12, 1), np.nan)
    qa, ra = panel.Q.sum(1), panel.R.sum(1)
    price = np.where(np.isnan(price), np.where(qa > 0, ra / np.where(qa > 0, qa, 1), np.nan), price)

    prof = pd.DataFrame({
        'item': panel.items, 'category': panel.meta['category'].to_numpy(),
        'production': panel.meta['production'].to_numpy(),
        'revenue_12m': rev12, 'qty_12m': q12, 'avg_monthly_qty': mean_q, 'std_monthly_qty': std_q,
        'active_months_12': active12, 'months_since_last_sale': since_last,
        'first_sale': np.where(first_idx >= 0, panel.months[np.maximum(first_idx, 0)], pd.NaT),
        'last_sale': np.where(last_idx >= 0, panel.months[np.maximum(last_idx, 0)], pd.NaT),
        'avg_unit_price': price})
    prof['cv'] = np.where(prof['avg_monthly_qty'] > 0, prof['std_monthly_qty'] / prof['avg_monthly_qty'], np.nan)

    # forecast demand over the next 3 / 6 / 12 months from the outlook
    fut_months = sorted(outlook_item['month'].unique())
    for h in (3, 6, 12):
        sub = outlook_item[outlook_item['month'].isin(fut_months[:h])].groupby('item')['forecast_qty'].sum()
        prof[f'fc_qty_next{h}'] = prof['item'].map(sub).fillna(0.0)

    # ABC on 12-month revenue; XYZ on demand variability
    order = prof['revenue_12m'].sort_values(ascending=False)
    share = order.cumsum() / max(order.sum(), 1)
    abc = pd.Series('C', index=prof.index)
    abc[share[share <= 0.80].index] = 'A'
    abc[share[(share > 0.80) & (share <= 0.95)].index] = 'B'
    abc[prof['revenue_12m'] <= 0] = 'No sales'
    prof['abc'] = abc
    xyz = np.where(prof['active_months_12'] < 3, 'Z', np.where(prof['cv'] < 0.5, 'X', np.where(prof['cv'] < 1.0, 'Y', 'Z')))
    prof['xyz'] = np.where(prof['revenue_12m'] <= 0, 'n/a', xyz)

    flag = np.select(
        [prof['months_since_last_sale'] >= 12,
         prof['months_since_last_sale'] >= 6,
         (prof['production'] != 'Continue') & (prof['revenue_12m'] > 0)],
        ['No sales 12+ months', 'Slow-moving (6-11 months)', 'Discontinued/TBA but still selling'], default='Healthy')
    prof['flag'] = flag
    return prof[prof['first_sale'].notna()].reset_index(drop=True)
