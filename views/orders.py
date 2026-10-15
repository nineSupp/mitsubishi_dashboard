"""Orders view (ported from main_dashboard.py; logic unchanged, now reads from the shared AppContext)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import BRAND_SEQ, WEEKDAYS, CURRENCY
from ui.model_panels import model_strip
from ui.components import back_bar, kpi_card, show_chart, show_table, csv_button, fmt_num, fmt_money, fmt_pct


def order_table(d):
    t = d.groupby('order', observed=True).agg(
        date=('date', 'first'), customer=('customer', 'first'), lines=('item', 'size'), units=('qty', 'sum'),
        gross=('gross', 'sum'), discount=('discount', 'sum'), revenue=('sales', 'sum'),
        status=('status', 'first'), segment=('segment', 'first')).reset_index()
    t['order'] = t['order'].astype(str)
    t['disc_pct'] = np.where(t['gross'] > 0, t['discount'] / t['gross'] * 100, np.nan)
    return t.sort_values('date', ascending=False).reset_index(drop=True)


def render(ctx):
    df_f, f_end, N_MONTHS = ctx.df_f, ctx.f_end, ctx.n_months
    back_bar('orders')
    model_strip('orders', ctx)
    st.markdown("## Orders")
    st.markdown("Order-level view: one row per sales order (several item lines are grouped into one order).")
    t = order_table(df_f)
    c = st.columns(4)
    with c[0]:
        kpi_card("Orders", f"{len(t):,}", f"≈ {len(t) / N_MONTHS:,.0f} / month", "neutral")
    with c[1]:
        kpi_card("Avg Lines / Order", f"{t['lines'].mean():.2f}", f"max {int(t['lines'].max())} lines", "neutral")
    with c[2]:
        kpi_card("Avg / Median Order Value", fmt_money(t['revenue'].mean()), f"median {fmt_money(t['revenue'].median())}", "neutral")
    with c[3]:
        kpi_card("Discounted Orders", fmt_pct((t['discount'] > 0).mean()), f"lost orders {fmt_pct((t['status'] == 'Loss').mean())}", "neutral")
    st.markdown("<br>", unsafe_allow_html=True)

    left, right = st.columns([2, 1])
    with left:
        st.markdown("### Orders per Month")
        pm = t.assign(month=t['date'].dt.to_period('M').dt.to_timestamp()).groupby('month').size().reset_index(name='orders')
        fig = px.bar(pm, x='month', y='orders', color_discrete_sequence=['#E60012'])
        show_chart(fig, legend=False, x_title="Month", y_title="Number of orders")
    with right:
        st.markdown("### Order Status")
        stt = t['status'].astype(str).value_counts().reset_index()
        stt.columns = ['status', 'orders']
        fig = px.pie(stt, names='status', values='orders', hole=0.6, color_discrete_sequence=BRAND_SEQ)
        fig.update_traces(textinfo='percent', textposition='inside')
        fig.update_layout(uniformtext_minsize=11, uniformtext_mode='hide')
        show_chart(fig, legend=True, legend_pos='right')

    left, right = st.columns(2)
    with left:
        st.markdown("### Order Value Distribution (log scale)")
        fig = px.histogram(t[t['revenue'] > 0], x='revenue', nbins=50, log_x=True, color_discrete_sequence=['#005BAC'])
        show_chart(fig, legend=False, x_title=f"Order value ({CURRENCY}, log scale)", y_title="Number of orders")
    with right:
        st.markdown("### Orders by Weekday")
        wd = t['date'].dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
        fig = px.bar(x=WEEKDAYS, y=wd.values, color_discrete_sequence=['#333333'])
        show_chart(fig, legend=False, x_title="Weekday", y_title="Number of orders")

    st.markdown("### Order List")
    f1, f2 = st.columns([2, 3])
    query = f1.text_input("Search order number")
    status_pick = f2.multiselect("Status (all if empty)", sorted(t['status'].astype(str).unique()))
    v = t
    if query.strip():
        v = v[v['order'].str.contains(query.strip(), case=False, regex=False)]
    if status_pick:
        v = v[v['status'].astype(str).isin(status_pick)]
    out = pd.DataFrame({
        'Order': v['order'], 'Date': v['date'].dt.date, 'Customer ID': v['customer'], 'Type': v['segment'].astype(str),
        'Status': v['status'].astype(str), 'Lines': v['lines'], 'Units': v['units'].round(0), 'Gross value': v['gross'].round(0),
        'Discount': v['discount'].round(0), 'Discount %': v['disc_pct'].round(1), 'Revenue': v['revenue'].round(0)})
    show_table(out.head(1000), height=420)
    st.caption(f"Showing the {min(len(out), 1000):,} most recent of {len(out):,} orders.")
    csv_button(out, "Download order list (CSV)", "orders.csv")
