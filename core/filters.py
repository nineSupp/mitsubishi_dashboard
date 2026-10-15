"""Sidebar = global interactive filters (same controls as the original dashboard)."""
import numpy as np
import pandas as pd
import streamlit as st

from core.context import AppContext
from ui.theme import sidebar_banner


def build_context(df_all, items_master, outputs):
    data_min, data_max = df_all['date'].min(), df_all['date'].max()
    all_months = pd.date_range(df_all['month'].min(), df_all['month'].max(), freq='MS')

    status_all = list(df_all['status'].cat.remove_unused_categories().cat.categories)
    defaults = {'f_date': (data_min.date(), data_max.date()), 'f_industry': [], 'f_category': [],
                'f_segment': 'All', 'f_status': status_all}

    def _reset_filters():
        """Runs before the page reruns: puts every Main Panel filter back to its original value."""
        for k, v in defaults.items():
            st.session_state[k] = list(v) if isinstance(v, list) else v

    with st.sidebar:
        sidebar_banner()
        date_range = st.date_input("Select Date Range", value=defaults['f_date'], min_value=data_min.date(),
                                   max_value=data_max.date(), key="f_date")
        industry_sel = st.multiselect("Industry (all if empty)",
                                      sorted(df_all['industry'].cat.remove_unused_categories().cat.categories), key="f_industry")
        category_sel = st.multiselect("Product Category (all if empty)",
                                      sorted(df_all['category'].cat.remove_unused_categories().cat.categories), key="f_category")
        segment_sel = st.selectbox("Customer Type", ["All", "VIP", "Non-VIP"], key="f_segment")
        status_sel = st.multiselect("Order Status (all if empty)", status_all, default=status_all, key="f_status")
        st.button("↺ Reset filters", key="reset_filters", on_click=_reset_filters, use_container_width=True)

    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        f_start, f_end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
    else:
        f_start, f_end = data_min, data_max

    mask = pd.Series(True, index=df_all.index)
    if status_sel:
        mask &= df_all['status'].isin(status_sel)
    if industry_sel:
        mask &= df_all['industry'].isin(industry_sel)
    if category_sel:
        mask &= df_all['category'].isin(category_sel)
    if segment_sel != "All":
        mask &= df_all['segment'] == segment_sel

    df_nd = df_all[mask]
    df_f = df_nd[(df_nd['date'] >= f_start) & (df_nd['date'] <= f_end)]

    with st.sidebar:
        st.caption(f"{len(df_f):,} of {len(df_all):,} order lines match the filters")

    if df_f.empty:
        st.warning("No data matches the current filters. Widen the date range or clear a filter in the sidebar.")
        st.stop()

    span = (f_end - f_start).days + 1
    p_end = f_start - pd.Timedelta(days=1)
    p_start = p_end - pd.Timedelta(days=span - 1)
    df_prev = df_nd[(df_nd['date'] >= p_start) & (df_nd['date'] <= p_end)] if p_start >= data_min else None
    if df_prev is not None and df_prev.empty:
        df_prev = None

    return AppContext(
        df_all=df_all, df_nd=df_nd, df_f=df_f, df_prev=df_prev, f_start=f_start, f_end=f_end,
        data_min=data_min, data_max=data_max, all_months=all_months,
        n_months=max(df_f['month'].nunique(), 1), items_master=items_master, outputs=outputs,
        filters=dict(industry=industry_sel, category=category_sel, segment=segment_sel, status=status_sel))
