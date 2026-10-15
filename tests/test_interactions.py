"""Click-to-drill callbacks and the add-data -> retrain -> what-if flow (isolated temp folders).
    python -m tests.test_interactions"""
import io, pathlib, tempfile, sys
import numpy as np, pandas as pd
from unittest.mock import MagicMock

from tests._paths import workbook
import tests.smoke_views as t            # installs the streamlit/plotly stand-ins
fake = t.fake
import config
import core.data as cd
from core import added_data as ad
from core.cache import load_outputs
from core.filters import build_context
from ui import components as comp
from views import forecast, growth, inventory, whatif, data_hub

ok = True
def check(name, cond):
    global ok
    ok &= bool(cond); print('OK  ' if cond else 'FAIL', name)

df, items, _ = cd.build_dataset(); out = load_outputs(0)
ctx = build_context(df, items, out)

# ---- 1. generic drill_chart: capture on_select, simulate a click, confirm the callback fires and the chart resets
rec = {}
fake.plotly_chart = lambda fig, **k: rec.update(k)
fake.session_state.clear()
picked = []
comp.drill_chart(MagicMock(), 'demo', lambda pts, fig: picked.append(pts[0]['x']))
key0 = rec['key']; fake.session_state[key0] = {'selection': {'points': [{'x': 'PLC'}]}}
rec['on_select']()
check('drill_chart calls on_pick with the clicked point', picked == ['PLC'])
comp.drill_chart(MagicMock(), 'demo', lambda pts, fig: None)
check('chart gets a fresh key after a pick (no stale highlight)', rec['key'] != key0)
fake.session_state[rec['key']] = {'selection': {'points': []}}
rec['on_select'](); check('empty click does nothing', picked == ['PLC'])

# ---- 2. each view's click handler changes the right selector
fake.session_state.clear()
fake.session_state['_fc_cats'] = ['PLC', 'SV']
forecast._pick_category([{'x': 'SV'}], None); check('forecast: click bar -> category level', fake.session_state['fc_level'] == 'SV')
forecast._pick_category([{'x': 'nope'}], None); check('forecast: unknown label ignored', fake.session_state['fc_level'] == 'SV')
forecast._set_level('Company total'); check('forecast: drill up', fake.session_state['fc_level'] == 'Company total')

fake.session_state['_gr_cats'] = ['PLC', 'HMI']
fig_v = MagicMock(); fig_v.data = [MagicMock(orientation='v')]
fig_h = MagicMock(); fig_h.data = [MagicMock(orientation='h')]
growth._pick_cat([{'x': 'HMI', 'y': 'zzz'}], fig_v); check('growth: vertical bar click', fake.session_state['gr_cat'] == 'HMI')
growth._pick_cat([{'x': 5, 'y': 'PLC'}], fig_h); check('growth: horizontal bar click', fake.session_state['gr_cat'] == 'PLC')
growth._drill_up(); check('growth: drill up', fake.session_state['gr_cat'] == 'All categories')

inventory._pick_segment([{'x': 'Z', 'y': 'A'}], None); check('inventory: bubble click -> A-Z', fake.session_state['inv_segment'] == 'A-Z')
f = MagicMock(); f.data = [MagicMock(), MagicMock()]; f.data[0].name = 'No sales 12+ months'; f.data[1].name = 'Slow-moving (6-11 months)'
inventory._pick_flag_category([{'x': 'PLC', 'curve_number': 1}], f)
check('inventory: stacked bar click -> flag + category', (fake.session_state['inv_flag'], fake.session_state['inv_flag_cat']) == ('Slow-moving (6-11 months)', 'PLC'))

# ---- 3. add data -> save -> merged into dashboard data -> retrain -> What-If on the updated baseline
tmp = pathlib.Path(tempfile.mkdtemp())
ad.ADDED_DIR = tmp / 'added'; config.OUTPUT_DIR = tmp / 'out'
orig_load = cd.load_added; cd.load_added = lambda i, c, added_dir=None: orig_load(i, c, tmp / 'added')
raw = ad.read_any(workbook(), 'TNIC Data_2025.xlsx')
clean, rep = ad.clean(raw, existing=df)
ad.save(clean, 'TNIC Data_2025.xlsx')
df2, _, _ = cd.build_dataset(include_added=True)
check('added rows merged into the dashboard data', (df2['source'] == 'added').sum() == len(clean) and df2['date'].max() >= pd.Timestamp('2026-03-31'))
ctx2 = build_context(df2, items, out)
fake.button = lambda *a, **k: k.get('key') == 'hub_train'
data_hub.render(ctx2)
check('retrain wrote the updated forecast files', all((tmp / 'out' / f).exists() for f in ('forecast_updated_company.csv', 'forecast_updated_category.csv', 'inventory_updated.csv')))
import core.cache as cc
upd = cc.load_updated(); o2 = dict(out); o2['updated'] = upd
check('updated forecast loads with a 12-month horizon', upd is not None and len(upd['company']) == 12)
ctx3 = build_context(df2, items, o2)
fake.button = lambda *a, **k: False
fake.radio = lambda label, options, index=0, **k: list(options)[-1]          # pick the last option = updated baseline
whatif.render(ctx3); check('what-if renders on the updated baseline', True)
data_hub.render(ctx3); check('add-data page renders with results', True)
# ---- 4. Main Panel reset button puts every filter back to its original value
fake.session_state.clear()
captured = {}
fake.button = lambda *a, **k: captured.update({k.get('key'): k.get('on_click')}) or False
ctx_r = build_context(df, items, out)
cb = captured['reset_filters']
fake.session_state.update(f_industry=['Automation'], f_category=['PLC'], f_segment='VIP', f_status=['Loss'],
                          f_date=(pd.Timestamp('2022-01-01').date(), pd.Timestamp('2022-06-30').date()))
cb()
check('reset restores every filter', fake.session_state['f_industry'] == [] and fake.session_state['f_category'] == []
      and fake.session_state['f_segment'] == 'All' and set(fake.session_state['f_status']) == {'Completed', 'On going', 'Loss'}
      and fake.session_state['f_date'] == (df['date'].min().date(), df['date'].max().date()))

# ---- 5. item drill-down in the forecast view (company -> category -> item), with and without the real-results overlay
fake.session_state.clear(); fake.button = lambda *a, **k: False
fake.selectbox = lambda label, options, index=0, **k: fake.session_state.get(k.get('key'), list(options)[index])
fake.radio = lambda label, options, index=0, **k: list(options)[index]
fake.toggle = lambda label, value=False, **k: True
top_item = out['item'].groupby('item')['forecast'].sum().idxmax()
cat_of = out['item'].loc[out['item']['item'] == top_item, 'category'].iloc[0]
fake.session_state.update(fc_level=cat_of, _fc_prev_level=cat_of, fc_item=top_item)
forecast.render(build_context(df, items, out)); check('forecast: item level renders', fake.session_state['fc_item'] == top_item)
fake.session_state.update(fc_level='Company total')
forecast.render(build_context(df, items, out)); check('forecast: changing level clears the item', fake.session_state['fc_item'] == '— none —')
forecast._pick_item([{'y': top_item}], None); check('forecast: clicking an item bar is ignored for unknown items', True)
fake.session_state['_fc_items'] = [top_item]; forecast._pick_item([{'y': top_item}], None)
check('forecast: clicking an item bar opens it', fake.session_state['fc_item'] == top_item)

sys.exit(0 if ok else 1)
