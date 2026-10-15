"""Pure-pandas analytics used by several views (no Streamlit)."""
import numpy as np
import pandas as pd

from core.data import realised


def fy_label(fy):
    return f"FY{int(fy)}"


def complete_years(df):
    """Fiscal years with all 12 months present (a part-year would look like a collapse in growth figures)."""
    n = df.groupby('fy')['month'].nunique()
    return [int(fy) for fy, m in n.items() if m >= 12]


def fy_revenue(df, by, years=None):
    """Realised revenue (Closed orders excluded) by fiscal year and one dimension. Returns pivot [by x FY].
    `years` limits the fiscal years (use complete_years of the full data)."""
    r = realised(df)
    if years is not None:
        r = r[r['fy'].isin(years)]
    t = r.groupby([by, 'fy'], observed=True)['sales'].sum().unstack('fy').fillna(0.0)
    t.index = t.index.astype(str)
    t.columns = [int(c) for c in t.columns]
    return t


def growth_table(pivot, min_share=0.0):
    """YoY growth for the latest two fiscal years and CAGR over the whole span."""
    fys = sorted(pivot.columns)
    last, prev, first = fys[-1], fys[-2], fys[0]
    t = pivot.copy()
    total_last = t[last].sum()
    t['share_last'] = t[last] / total_last if total_last else np.nan
    t['yoy'] = np.where(t[prev] > 0, t[last] / t[prev] - 1, np.nan)
    years = last - first
    t['cagr'] = np.where((t[first] > 0) & (t[last] > 0) & (years > 0), (t[last] / t[first]) ** (1 / years) - 1, np.nan)
    if min_share:
        t = t[t[prev] / max(t[prev].sum(), 1) >= min_share]
    return t


def item_growth(df, fy_a, fy_b, category=None, min_revenue=0.0):
    """Revenue change per item between two fiscal years."""
    r = realised(df)
    if category and category != 'All categories':
        r = r[r['category'].astype(str) == category]
    p = r[r['fy'].isin([fy_a, fy_b])].groupby(['item', 'fy'], observed=True)['sales'].sum().unstack('fy').fillna(0.0)
    for c in (fy_a, fy_b):
        if c not in p.columns:
            p[c] = 0.0
    p = p.reset_index()
    p['item'] = p['item'].astype(str)
    p['change'] = p[fy_b] - p[fy_a]
    p['change_pct'] = np.where(p[fy_a] > 0, p[fy_b] / p[fy_a] - 1, np.nan)
    return p[(p[fy_a] + p[fy_b]) >= min_revenue]


def category_accuracy(cat_df):
    """Per-category accuracy of the FY2025 backtest (monthly), plus full-year bias."""
    rows = []
    for c, g in cat_df.groupby('category'):
        a, f = g['actual'].to_numpy(float), g['forecast'].to_numpy(float)
        den = np.abs(a).sum()
        rows.append(dict(category=c, actual=a.sum(), forecast=f.sum(),
                         bias=(f.sum() - a.sum()) / a.sum() if a.sum() else np.nan,
                         accuracy=max(1 - np.abs(a - f).sum() / den, 0) if den else np.nan))
    return pd.DataFrame(rows).sort_values('actual', ascending=False)


def company_accuracy(company_df):
    """Monthly accuracy (1-WAPE) and full-year error of a backtest company table."""
    a, f = company_df['actual'].to_numpy(float), company_df['forecast'].to_numpy(float)
    return dict(monthly=max(1 - np.abs(a - f).sum() / a.sum(), 0), year_error=f.sum() / a.sum() - 1,
                forecast=f.sum(), actual=a.sum())
