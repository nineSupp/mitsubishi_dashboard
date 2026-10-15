"""Mitsubishi Electric x TNIC Team 6 dashboard: one page, drill down by clicking a question card.

Run:  streamlit run app.py
"""
import streamlit as st

import config
from ui.theme import page_icon, inject_theme

st.set_page_config(page_title='Mitsubishi x TNIC Team 6 Dashboard', page_icon=page_icon(),
                   layout='wide', initial_sidebar_state='expanded')
inject_theme()
st.session_state['_chart_n'] = 0

from core import watchdog   # noqa: E402
watchdog.start()            # closes the launcher window when the last browser tab is closed (launcher only)

from core.cache import data_files_present, load_dataset, load_outputs, stamps  # noqa: E402
from core.filters import build_context                                          # noqa: E402
from ui.components import current_view                                          # noqa: E402
from views import (home, forecast, inventory, growth, accuracy, whatif, data_hub,        # noqa: E402
                   products, customers, industries, orders, import_data)

VIEWS = {
    'home': home.render, 'forecast': forecast.render, 'inventory': inventory.render, 'growth': growth.render,
    'accuracy': accuracy.render, 'whatif': whatif.render, 'upload': data_hub.render, 'import': import_data.render, 'products': products.render, 'customers': customers.render,
    'industries': industries.render, 'orders': orders.render,
}

if not data_files_present():
    import_data.render(None)          # first run: welcome screen with the two ways to load the data
    st.stop()

data_stamp, out_stamp = stamps()
df_all, items_master = load_dataset(data_stamp, st.session_state.get('use_added', True))
outputs = load_outputs(out_stamp)
ctx = build_context(df_all, items_master, outputs)

VIEWS.get(current_view(), home.render)(ctx)
