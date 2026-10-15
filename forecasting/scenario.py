"""What-If arithmetic on top of the baseline forecast (assumption-driven, not a statistical forecast)."""
import numpy as np
import pandas as pd


def run_scenario(cat_df, p):
    """cat_df: month, category, forecast (revenue), forecast_qty.
    p keys: demand_pct, price_pct, discount_pp, base_discount, elasticity, lost_share, lost_pct, new_pct, categories.
    Levers are applied in order: demand -> price/discount (with volume response) -> lost customers -> new items."""
    d = cat_df.copy()
    cats = set(p.get('categories') or [])
    aff = d['category'].isin(cats).to_numpy() if cats else np.ones(len(d), bool)

    bd = float(np.clip(p['base_discount'], 0, 0.95))
    nd = float(np.clip(bd + p['discount_pp'] / 100, 0, 0.95))
    price_mult = (1 + p['price_pct'] / 100) * (1 - nd) / (1 - bd)         # net price vs today
    vol_mult = price_mult ** p['elasticity'] if price_mult > 0 else 1.0     # constant-elasticity volume response
    demand_mult = 1 + p['demand_pct'] / 100
    cust_mult = 1 - p['lost_share'] * p['lost_pct'] / 100

    r0, q0 = d['forecast'].to_numpy(float), d['forecast_qty'].to_numpy(float)
    r1, q1 = np.where(aff, r0 * demand_mult, r0), np.where(aff, q0 * demand_mult, q0)
    r2, q2 = np.where(aff, r1 * price_mult * vol_mult, r1), np.where(aff, q1 * vol_mult, q1)
    r3, q3 = np.where(aff, r2 * cust_mult, r2), np.where(aff, q2 * cust_mult, q2)
    r4, q4 = np.where(aff, r3 + p['new_pct'] / 100 * r0, r3), np.where(aff, q3 + p['new_pct'] / 100 * q0, q3)

    d['scenario'], d['scenario_qty'] = r4, q4
    monthly = d.groupby('month', as_index=False).agg(baseline=('forecast', 'sum'), scenario=('scenario', 'sum'),
                                                      qty_baseline=('forecast_qty', 'sum'), qty_scenario=('scenario_qty', 'sum'))
    by_cat = d.groupby('category', as_index=False).agg(baseline=('forecast', 'sum'), scenario=('scenario', 'sum'))
    by_cat['change_pct'] = np.where(by_cat['baseline'] > 0, by_cat['scenario'] / by_cat['baseline'] - 1, np.nan)
    steps = [('Baseline forecast', r0.sum()), ('Demand change', r1.sum() - r0.sum()),
             ('Price / discount (with volume response)', r2.sum() - r1.sum()), ('Lost customers', r3.sum() - r2.sum()),
             ('New items', r4.sum() - r3.sum())]
    return dict(monthly=monthly, by_category=by_cat.sort_values('baseline', ascending=False), steps=steps,
                price_mult=price_mult, vol_mult=vol_mult, net_discount=nd)
