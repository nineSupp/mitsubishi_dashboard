"""Headless smoke test: runs every view with a stand-in for streamlit/plotly so pandas logic, column names
and imports are exercised without a browser.   python -m tests.smoke_views"""
import sys, types, contextlib
from unittest.mock import MagicMock


WIDGETS = {'radio', 'selectbox', 'multiselect', 'slider', 'toggle', 'text_input', 'button', 'file_uploader',
           'columns', 'tabs', 'container', 'expander'}


class _Ctx:
    """Stand-in for `with st.columns(...)[i]:` objects; widgets called on it behave like st.<widget>."""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name):
        if name.startswith('__'): raise AttributeError(name)
        return getattr(fake, name) if name in WIDGETS else MagicMock()


class FakeSt(types.ModuleType):
    def __init__(self):
        super().__init__('streamlit'); self.session_state = {}; self.sidebar = _Ctx()
        self.errors = []

    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec); return [_Ctx() for _ in range(n)]
    def tabs(self, names): return [_Ctx() for _ in names]
    def radio(self, label, options, index=0, **k): return list(options)[index]
    def selectbox(self, label, options, index=0, **k): return list(options)[index]
    def multiselect(self, label, options, default=None, **k): return list(default or [])
    def slider(self, label, *a, **k): return a[2] if len(a) > 2 else k.get('value')
    def toggle(self, label, value=False, **k): return value
    def text_input(self, *a, **k): return ''
    def button(self, *a, **k): return False
    def file_uploader(self, *a, **k): return None
    def container(self, **k): return _Ctx()
    def expander(self, *a, **k): return _Ctx()
    def error(self, msg, **k): self.errors.append(msg)
    def warning(self, msg, **k): self.errors.append(msg)
    def cache_data(self, *a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]
    def __getattr__(self, name):
        if name.startswith('__'): raise AttributeError(name)
        return MagicMock()


fake = FakeSt()
sys.modules['streamlit'] = fake
sys.modules['streamlit.components'] = types.ModuleType('streamlit.components')
sys.modules['streamlit.components.v1'] = MagicMock()
for m in ('plotly', 'plotly.express', 'plotly.graph_objects'):
    sys.modules[m] = MagicMock()

import config                                        # noqa: E402
from core.data import build_dataset                  # noqa: E402
from core.cache import load_outputs                  # noqa: E402
from core.filters import build_context               # noqa: E402
from views import (home, forecast, inventory, growth, accuracy, whatif, data_hub, products,  # noqa: E402
                   customers, industries, orders, import_data)

if __name__ == '__main__':
    df, items, _ = build_dataset()
    outputs = load_outputs(0)
    ctx = build_context(df, items, outputs)
    ok = True
    for name, mod in [('home', home), ('forecast', forecast), ('inventory', inventory), ('growth', growth),
                      ('accuracy', accuracy), ('whatif', whatif), ('upload', data_hub), ('import', import_data), ('products', products), ('customers', customers),
                      ('industries', industries), ('orders', orders)]:
        try:
            mod.render(ctx); print('OK  ', name)
        except Exception as e:                       # noqa: BLE001
            ok = False; import traceback; print('FAIL', name, repr(e)); traceback.print_exc()
    # the dashboard's data must stop at the end of FY2024 (FY2025 actuals are comparison-only)
    assert df['date'].max() < __import__('pandas').Timestamp('2025-04-01'), 'FY2025 leaked into the dashboard data'
    print('OK   data ends', df['date'].max().date())
    # forecast view: another level with the "compare with real FY2025" switch on
    for lvl in ['PLC', 'SV']:
        fake.selectbox = lambda label, options, index=0, _l=lvl, **k: _l if _l in list(options) else list(options)[index]
        fake.toggle = lambda label, value=False, **k: True
        try:
            forecast.render(ctx); print('OK   forecast compare=on', lvl)
        except Exception as e:                       # noqa: BLE001
            ok = False; import traceback; print('FAIL forecast', lvl, repr(e)); traceback.print_exc()
    sys.exit(0 if ok else 1)
