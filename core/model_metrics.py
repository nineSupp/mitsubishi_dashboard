"""Accuracy / back-check numbers for each method, computed from the saved evaluation and the FY2025 comparison files.
Returns {method_key: dict(stats=[(label, value), ...], note=str)}. Pure pandas (no Streamlit)."""
import numpy as np
import pandas as pd

from core.analytics import company_accuracy
from core.data import realised
from core.model_registry import METHODS
from forecasting.planning import plan_reorder


def _acc(ev, model, level, fold):
    s = ev[(ev['Model'] == model) & (ev['Level'] == level) & (ev['Target'] == 'Revenue') & (ev['Fold'] == fold)]['Accuracy']
    return f"{s.iloc[0] * 100:.0f}%" if len(s) else "–"


def _processing_report():
    """Counts from the last import run (data/processed/processing_report.json), or None."""
    import json
    import config
    p = config.PROCESSED_DIR / 'processing_report.json'
    if not p.exists():
        return None
    try:
        rep = json.loads(p.read_text(encoding='utf-8'))
        steps = {s['step']: s for s in rep['steps']}
        rep['summary_stages'] = dict(after_cleaning=steps['1.7']['rows'], after_transform=steps['2.10']['rows'],
                                     features_added=int(str(steps['2.10']['detail']).split('(')[1].split(' ')[0]))
        return rep
    except Exception:                                                  # noqa: BLE001
        return None


def method_metrics(outputs, df_all):
    m = {k: dict(stats=[], note='') for k in METHODS}
    m['descriptive']['note'] = 'Nothing is predicted, so there is no accuracy to score. Numbers are exact sums of your orders.'
    m['dataload']['note'] = 'Not a forecast. It rejects rows it cannot trust and tells you how many.'
    m['scenario']['note'] = "What-if results come from your assumptions, so they cannot be scored. Their baseline is the Gradient Boosting forecast."
    rep = _processing_report()
    for k in ('p_clean', 'p_features', 'p_encode'):
        m[k]['note'] = ('Same steps as the notebooks; a test checks the output is identical to running the notebooks. '
                        'Nothing is predicted, so there is no accuracy to score.')
    if rep:
        s = rep['summary_stages']
        m['p_clean']['stats'] = [('Rows read', f"{rep['rows_in']:,}"), ('Rows kept', f"{s['after_cleaning']:,}")]
        m['p_features']['stats'] = [('Rows', f"{s['after_transform']:,}"), ('Columns added', f"{s['features_added']}")]
        m['p_encode']['stats'] = [('Final rows', f"{rep['rows_out']:,}"), ('Final columns', f"{rep['columns']}")]
    if outputs is None:
        for k in ('gbm', 'mix', 'abcxyz', 'safety', 'flags', 'growth', 'backtest'):
            m[k]['note'] = 'Run scripts.train_forecasts to see accuracy.'
        return m
    ev, inv, co, cat = outputs['eval'], outputs['inventory'], outputs['company'], outputs['category']

    acc = company_accuracy(co)
    g = METHODS['gbm']
    m['gbm'] = dict(stats=[('Validation FY2024', _acc(ev, g['eval_name'], g['eval_level'], 'FY2024')),
                           ('Final test FY2025', _acc(ev, g['eval_name'], g['eval_level'], 'FY2025')),
                           ('FY2025 full-year total', f"{acc['year_error'] * 100:+.1f}%")],
                    note='Accuracy = 1 − WAPE, company revenue by month.')
    x = METHODS['mix']
    m['mix'] = dict(stats=[('Validation FY2024', _acc(ev, x['eval_name'], x['eval_level'], 'FY2024')),
                           ('Final test FY2025', _acc(ev, x['eval_name'], x['eval_level'], 'FY2025'))],
                    note='Accuracy = 1 − WAPE, revenue by category and month. Item-by-month is much lower (about 15-30%).')

    a_share = inv.loc[inv['abc'] == 'A', 'actual_fy25_revenue'].sum() / max(inv['actual_fy25_revenue'].sum(), 1e-9)
    m['abcxyz'] = dict(stats=[('A-class share of real FY2025 revenue', f"{a_share * 100:.0f}%")],
                       note='Classes were set in March 2025 (A = 80% of revenue then). Higher means the classes held up.')
    act = inv[(inv['revenue_12m'] > 0) & (inv['actual_fy25_qty'] > 0)]      # items that really sold in FY2025
    p = plan_reorder(act, 2.0, 0.95, 3)
    cover = float(((act['actual_fy25_qty'] / 12 * 2) <= p['rop']).mean())
    m['safety'] = dict(stats=[('Reorder point covered real demand', f"{cover * 100:.0f}% of items that sold")],
                       note='Check at 2-month lead time, 95% service: real average FY2025 lead-time demand ≤ reorder point.')
    dead = inv[inv['flag'] == 'No sales 12+ months']
    stayed = float((dead['actual_fy25_qty'] <= 0).mean()) if len(dead) else np.nan
    m['flags'] = dict(stats=[('Dead flags that stayed dead in FY2025', f"{stayed * 100:.0f}%")],
                      note='Of items with no sale for 12+ months (Mar 2025), the share that still did not sell in FY2025.')

    r24 = realised(df_all)
    r24 = r24[r24['fy'] == 2024].groupby('category', observed=True)['sales'].sum()
    r24.index = r24.index.astype(str)
    big = r24[r24 / max(r24.sum(), 1) >= 0.01].index
    cs = cat.groupby('category')[['forecast', 'actual']].sum().reindex(big).dropna()
    ok = int((np.sign(cs['forecast'] - r24.reindex(cs.index)) == np.sign(cs['actual'] - r24.reindex(cs.index))).sum())
    m['growth'] = dict(stats=[('Growth direction right (FY2025 vs FY2024)', f"{ok} of {len(cs)} categories")],
                       note='Year-on-year growth from history is exact. This checks the FY2025 category outlook against real results.')
    m['backtest']['stats'] = [('Validation folds', 'FY2023, FY2024'), ('Final test', 'FY2025')]
    m['backtest']['note'] = 'Every candidate is trained only on earlier months and scored on the next full year.'
    return m


def team_model_rows(ev):
    """Scores for the team's four quantity models: own recursive forecast (units per item-month) and as the splitter of
    the company forecast (category revenue). Missing models (library not installed) come back with None scores."""
    from core.model_registry import TEAM_MODELS

    def pick(model, level, target, fold):
        s = ev[(ev['Model'] == model) & (ev['Level'] == level) & (ev['Target'] == target) & (ev['Fold'] == fold)]['Accuracy']
        return float(s.iloc[0]) if len(s) else None

    rows = []
    for t in TEAM_MODELS:
        rows.append(dict(
            name=t['name'], desc=t['desc'], config=t['config'],
            units_val=pick(t['eval'], 'SKU x month', 'Quantity', 'FY2024'), units_final=pick(t['eval'], 'SKU x month', 'Quantity', 'FY2025'),
            cat_val=pick(t['mix'], 'Category x month', 'Revenue', 'FY2024'), cat_final=pick(t['mix'], 'Category x month', 'Revenue', 'FY2025'),
            ran=pick(t['eval'], 'SKU x month', 'Quantity', 'FY2024') is not None))
    flat = dict(units_val=pick('Flat 12-month average', 'SKU x month', 'Quantity', 'FY2024'),
                units_final=pick('Flat 12-month average', 'SKU x month', 'Quantity', 'FY2025'),
                cat_val=pick('Top-down: company GBM + flat-average mix', 'Category x month', 'Revenue', 'FY2024'),
                cat_final=pick('Top-down: company GBM + flat-average mix', 'Category x month', 'Revenue', 'FY2025'))
    return rows, flat
