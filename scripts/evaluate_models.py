"""Two-stage backtest.

Stage 1 (validation, history only): FY2023 = train FY2021-22, FY2024 = train FY2021-23. Models are ranked here.
Stage 2 (final test): FY2025 = train FY2021-24, scored against the real FY2025 orders in TNIC_Data_2025.xlsx.
In every fold the models only see months BEFORE the forecast year.

    python -m scripts.evaluate_models            # everything (random forests take a few minutes)
    python -m scripts.evaluate_models --fast     # skip the random-forest models
"""
import argparse, time
import numpy as np
import pandas as pd

import config
from core.data import build_dataset
from forecasting.panel import build_panel, outlier_cap, cap_outliers
from forecasting import item_model as im
from forecasting.evaluation import score_levels
from forecasting.metrics import summarise
from forecasting.series_models import SERIES_MODELS, predict_series

FOLDS = {'FY2023': 24, 'FY2024': 36, 'FY2025': 48}      # n training months before each test year


def run_fold(panel, n_train, fast):
    cap = outlier_cap(panel, n_train)
    pc = cap_outliers(panel, cap)
    ctx = im.Context(pc, n_train)
    price = im._last_price(pc, n_train)
    fcs = dict(im.baseline_forecasts(pc, ctx, n_train))

    X, y = im.training_set(pc, ctx, n_train)
    avail = im.available_kinds()
    kinds = [('HGB log-target, recursive', 'hgb', 'HGB log-target'), ('HGB Poisson, recursive', 'hgb_poisson', 'HGB Poisson')]
    if not fast:
        kinds += [('RandomForest (recursive)', 'rf', 'RandomForest'), ('Hurdle two-stage (recursive)', 'hurdle', 'Hurdle')]
        for label, kind, short in (('LightGBM (recursive, Tweedie)', 'lgbm', 'LightGBM'), ('XGBoost (recursive, Tweedie)', 'xgb', 'XGBoost')):
            if kind in avail:
                kinds.append((label, kind, short))
    shorts = {}
    for label, kind, short in kinds:
        m = im.ItemDemandModel(kind, n_estimators=100).fit(X, y)
        fcs[label], _ = im.recursive_forecast(m, pc, ctx, n_train)
        shorts[label] = short
    Xd, yd = im.direct_training_set(pc, ctx, n_train)
    dm = im.ItemDemandModel('hgb_poisson').fit(Xd, yd)
    fcs['HGB Poisson, direct multi-horizon'], _ = im.direct_forecast(dm, pc, ctx, n_train)

    # hierarchical variants: company revenue from the series model, mix across items from the item-level forecast
    comp_rev = predict_series(panel.R.sum(0)[:n_train], panel.months[:n_train], 12, 'gbm')

    def topdown(qty_fc):
        rev = (qty_fc * price[:, None]).sum(0)
        return qty_fc * np.where(rev > 0, comp_rev / np.where(rev > 0, rev, 1), 1.0)[None, :]

    fcs['Top-down: company GBM + flat-average mix'] = topdown(fcs['Flat 12-month average'])
    for label, short in shorts.items():
        fcs[f'Top-down: company GBM + {short} mix'] = topdown(fcs[label])
    # simple 50/50 blend of the best learned model and the flat average
    fcs['Blend: HGB Poisson recursive + flat average'] = 0.5 * fcs['HGB Poisson, recursive'] + 0.5 * fcs['Flat 12-month average']

    rows = []
    for label, fc in fcs.items():
        rows += score_levels(panel, n_train, fc, price, label)
    return rows, fcs, price


def run_series_fold(panel, n_train):
    """Top-down: model the company monthly revenue / quantity series directly."""
    rows = []
    for target, mat in (('Revenue', panel.R), ('Quantity', panel.Q)):
        series = mat.sum(0)
        months = panel.months[:n_train]
        actual = series[n_train:n_train + 12]
        for label, key in SERIES_MODELS.items():
            p = predict_series(series[:n_train], months, 12, key)
            for level, a, f in (('Company x month', actual, p), ('Company x year', actual.sum()[None], p.sum()[None])):
                d = summarise(a, f); d.update(Model=label, Level=level, Target=target); rows.append(d)
    return rows


def run_one(fold, fast):
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    df, _, _ = build_dataset(include_actuals=True)   # FY2025 actuals are used only as the answer key
    panel = build_panel(df)
    n_train = FOLDS[fold]
    t0 = time.time()
    rows, fcs, price = run_fold(panel, n_train, fast)
    rows += run_series_fold(panel, n_train)
    for r in rows:
        r['Fold'] = fold
    pd.DataFrame(rows).to_csv(config.OUTPUT_DIR / f'_eval_{fold}.csv', index=False)
    if fold == 'FY2025':
        np.savez_compressed(config.OUTPUT_DIR / '_eval_fy25_forecasts.npz', items=panel.items, price=price, **fcs)
    print(f'{fold}: done in {time.time() - t0:.0f}s', flush=True)


def combine():
    parts = [pd.read_csv(p) for p in sorted(config.OUTPUT_DIR.glob('_eval_FY*.csv'))]
    res = pd.concat(parts)[['Fold', 'Model', 'Level', 'Target', 'Accuracy', 'WAPE', 'Bias', 'MAE']]
    res.to_csv(config.OUTPUT_DIR / 'eval_all_folds.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_columns', 30)
    for tgt, lvl in (('Revenue', 'Company x year'), ('Revenue', 'Company x month'), ('Revenue', 'Category x month'),
                     ('Revenue', 'SKU x month')):
        t = res[(res.Target == tgt) & (res.Level == lvl)].pivot_table(index='Model', columns='Fold', values='Accuracy')
        t['validation mean (FY23+FY24)'] = t[['FY2023', 'FY2024']].mean(axis=1)
        print(f'\n=== {tgt} / {lvl}: accuracy ===\n', t.sort_values('validation mean (FY23+FY24)', ascending=False).round(3).to_string())


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--fast', action='store_true'); ap.add_argument('--fold', choices=list(FOLDS))
    ap.add_argument('--combine', action='store_true')
    a = ap.parse_args()
    if a.fold:
        run_one(a.fold, a.fast)
    if a.combine:
        combine()
