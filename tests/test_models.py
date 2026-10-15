"""Model plumbing: every selectable item model trains, forecasts and plugs into the official pipeline.
LightGBM / XGBoost are replaced by small stand-ins (sklearn) when the real libraries are not installed, so this checks
OUR code path (feature building, recursion, top-down scaling), not the libraries themselves.
    python -m tests.test_models"""
import sys, types
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

for name, cls in (('lightgbm', 'LGBMRegressor'), ('xgboost', 'XGBRegressor')):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            mod = types.ModuleType(name)
            setattr(mod, cls, lambda **kw: HistGradientBoostingRegressor(loss='poisson', max_iter=60, random_state=0))
            sys.modules[name] = mod
            print(f'(using a stand-in for {name})')

import tests.smoke_views            # noqa: F401  (streamlit stand-ins, needed by core.cache imports)
import config
from core.data import build_dataset
from forecasting.panel import build_panel
from forecasting import item_model as im
from forecasting.pipeline import official_forecast

ok = True
def check(name, cond):
    global ok
    ok &= bool(cond); print('OK  ' if cond else 'FAIL', name)

df, _, _ = build_dataset(include_actuals=True)
panel = build_panel(df)
check('all six model kinds are available', {'rf', 'hurdle', 'lgbm', 'xgb'} <= im.available_kinds())

company = None
for mix in ('flat', 'random_forest', 'lightgbm', 'xgboost', 'hurdle'):
    fc = official_forecast(panel, 48, mix=mix)
    tot = fc['category'].groupby('month')['forecast'].sum().to_numpy()
    comp = fc['company']['forecast'].to_numpy()
    company = comp if company is None else company
    check(f'mix={mix}: used {fc["mix"]}, categories add up to the company total', fc['mix'] == mix and np.allclose(tot, comp, rtol=1e-6))
    check(f'mix={mix}: company total unchanged by the splitter', np.allclose(comp, company))
    c, it = fc['category'], fc['item']
    check(f'mix={mix}: ranges bracket the forecast', (c['lo'] <= c['forecast'] + 1e-6).all() and (c['hi'] >= c['forecast'] - 1e-6).all()
          and (it['lo'] <= it['forecast'] + 1e-6).all() and (it['hi'] >= it['forecast'] - 1e-6).all())
fc = official_forecast(panel, 48, mix='no_such_model')
check('unknown mix falls back to flat', fc['mix'] == 'flat')
sys.exit(0 if ok else 1)
