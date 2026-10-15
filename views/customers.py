"""Customers view (ported from main_dashboard.py; logic unchanged, now reads from the shared AppContext)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import BRAND_SEQ, WEEKDAYS, CURRENCY
from ui.model_panels import model_strip
from ui.components import back_bar, kpi_card, show_chart, show_table, csv_button, fmt_num, fmt_money, fmt_pct


def customer_table(d, ref_date):
    t = d.groupby('customer').agg(
        revenue=('sales', 'sum'), orders=('order', 'nunique'), units=('qty', 'sum'), items=('item', 'nunique'),
        gross=('gross', 'sum'), disc=('discount', 'sum'), first=('date', 'min'), last=('date', 'max'),
        segment=('segment', 'first')).reset_index()
    t['recency'] = (ref_date - t['last']).dt.days
    t['aov'] = np.where(t['orders'] > 0, t['revenue'] / t['orders'], np.nan)
    t['disc_pct'] = np.where(t['gross'] > 0, t['disc'] / t['gross'], np.nan)
    t['share'] = t['revenue'] / t['revenue'].sum() * 100 if t['revenue'].sum() else 0

    def score(s, ascending):
        if len(s) < 5:
            return pd.Series(3, index=s.index)
        return pd.qcut(s.rank(method='first', ascending=ascending), 5, labels=False) + 1

    t['R'] = score(t['recency'], False)   # 5 = bought most recently
    t['F'] = score(t['orders'], True)     # 5 = most orders
    t['M'] = score(t['revenue'], True)    # 5 = highest revenue
    t['rfm'] = np.select(
        [(t.R >= 4) & (t.F >= 4) & (t.M >= 4), (t.R >= 3) & (t.F >= 4), (t.R >= 4) & (t.F <= 2),
         (t.R <= 2) & (t.F >= 3), (t.R <= 2) & (t.F <= 2)],
        ['Champions', 'Loyal', 'New / Promising', 'At Risk', 'Lost'], default='Needs Attention')
    return t.sort_values('revenue', ascending=False).reset_index(drop=True)


def render(ctx):
    df_f, f_end, N_MONTHS = ctx.df_f, ctx.f_end, ctx.n_months
    back_bar('customers')
    model_strip('customers', ctx)
    st.markdown("## Customers")
    st.markdown("Who buys, how much and who is drifting away. Segments use RFM scoring (Recency, Frequency, Monetary).")
    t = customer_table(df_f, f_end)
    repeat = (t['orders'] >= 2).mean()
    c = st.columns(4)
    with c[0]:
        kpi_card("Customers", f"{len(t):,}", "buying in selected period", "neutral")
    with c[1]:
        kpi_card("VIP Customers", f"{int((t['segment'] == 'VIP').sum()):,}", fmt_pct((t['segment'] == 'VIP').mean()) + " of customers", "neutral")
    with c[2]:
        kpi_card("Repeat Rate", fmt_pct(repeat), "customers with 2+ orders", "neutral")
    with c[3]:
        kpi_card("Avg Revenue / Customer", fmt_money(t['revenue'].mean()), f"median {fmt_money(t['revenue'].median())}", "neutral")
    st.markdown("<br>", unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("### Top 15 Customers by Revenue")
        top = t.head(15).sort_values('revenue')
        fig = px.bar(top, x='revenue', y=top['customer'].astype(str), orientation='h', color='segment',
                     color_discrete_map={'VIP': '#E60012', 'Non-VIP': '#005BAC'})
        fig.update_yaxes(type='category')
        show_chart(fig, height=400, x_title=f"Revenue ({CURRENCY})", y_title="Customer ID", money='x')
    with right:
        st.markdown("### RFM Segments")
        seg = t.groupby('rfm').agg(customers=('customer', 'count'), revenue=('revenue', 'sum')).reset_index()
        fig = px.pie(seg, names='rfm', values='customers', hole=0.55, color_discrete_sequence=BRAND_SEQ)
        fig.update_traces(textinfo='value', textposition='inside')
        fig.update_layout(uniformtext_minsize=11, uniformtext_mode='hide')
        show_chart(fig, height=400, legend=True, legend_pos='right')

    st.markdown("### Customer List")
    f1, f2 = st.columns([2, 3])
    query = f1.text_input("Search customer ID")
    seg_pick = f2.multiselect("RFM segment (all if empty)", sorted(t['rfm'].unique()))
    v = t
    if query.strip():
        v = v[v['customer'].astype(str).str.contains(query.strip(), regex=False)]
    if seg_pick:
        v = v[v['rfm'].isin(seg_pick)]
    out = pd.DataFrame({
        'Customer ID': v['customer'], 'Type': v['segment'].astype(str), 'RFM segment': v['rfm'],
        'Revenue': v['revenue'].round(0), 'Share of revenue (%)': v['share'].round(2), 'Orders': v['orders'],
        'Units': v['units'].round(0), 'Avg order value': v['aov'].round(0), 'Unique items': v['items'],
        'Avg discount %': (v['disc_pct'] * 100).round(1), 'Last purchase': v['last'].dt.date, 'Days since last': v['recency'],
    })
    show_table(out.head(1000), height=420)
    st.caption(f"Showing {min(len(out), 1000):,} of {len(out):,} customers.")
    csv_button(out, "Download customer list (CSV)", "customers.csv")
