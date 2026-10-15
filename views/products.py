"""Product performance view (ported from main_dashboard.py; logic unchanged, now reads from the shared AppContext)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import BRAND_SEQ, WEEKDAYS, CURRENCY
from ui.model_panels import model_strip
from ui.components import back_bar, kpi_card, show_chart, show_table, csv_button, fmt_num, fmt_money, fmt_pct


def item_table(d):
    t = d.groupby('item', observed=True).agg(
        revenue=('sales', 'sum'), units=('qty', 'sum'), orders=('order', 'nunique'), customers=('customer', 'nunique'),
        gross=('gross', 'sum'), disc=('discount', 'sum'), category=('category', 'first'), production=('production', 'first'),
    ).reset_index()
    t['item'] = t['item'].astype(str)
    t['avg_price'] = np.where(t['units'] > 0, t['revenue'] / t['units'], np.nan)
    t['disc_pct'] = np.where(t['gross'] > 0, t['disc'] / t['gross'], np.nan)
    t = t.sort_values('revenue', ascending=False).reset_index(drop=True)
    total = t['revenue'].sum()
    t['cum_share'] = t['revenue'].cumsum() / total if total else 0
    # ABC class: A = items that make the first 80% of revenue, B = next 15%, C = last 5%
    t['abc'] = np.where(t['cum_share'] <= 0.80, 'A', np.where(t['cum_share'] <= 0.95, 'B', 'C'))
    return t


def render(ctx):
    df_f, f_end, N_MONTHS = ctx.df_f, ctx.f_end, ctx.n_months
    back_bar('products')
    model_strip('products', ctx)
    st.markdown("## Product Performance")
    st.markdown("Best and worst sellers, category mix and revenue concentration (ABC analysis).")
    c1, c2, c3 = st.columns(3)
    rank_by = c1.selectbox("Rank items by", ["Revenue", "Units sold", "Orders"])
    top_n = c2.slider("Items to show", 5, 25, 10)
    skip_zero = c3.toggle("Ignore items with zero value", value=True)
    key = {"Revenue": "revenue", "Units sold": "units", "Orders": "orders"}[rank_by]
    rank_title = f"Revenue ({CURRENCY})" if key == "revenue" else rank_by

    t = item_table(df_f)
    a_items = int((t['abc'] == 'A').sum())
    disc_rev = t.loc[t['production'] == 'Discontinue', 'revenue'].sum() / t['revenue'].sum() if t['revenue'].sum() else np.nan
    c = st.columns(4)
    with c[0]:
        kpi_card("Items Sold", f"{len(t):,}", f"{len(t) / max(N_MONTHS, 1):,.0f} avg active / month-span", "neutral")
    with c[1]:
        kpi_card("A-Class Items", f"{a_items:,}", f"{fmt_pct(a_items / len(t))} of items = 80% revenue", "neutral")
    with c[2]:
        kpi_card("Zero-Revenue Items", f"{int((t['revenue'] <= 0).sum()):,}", "sold with no revenue", "neutral")
    with c[3]:
        kpi_card("Discontinued Revenue", fmt_pct(disc_rev), "share from discontinued items", "neutral")
    st.markdown("<br>", unsafe_allow_html=True)

    pool = t[t[key] > 0] if skip_zero else t
    top = pool.nlargest(top_n, key)
    bottom = pool.nsmallest(top_n, [key, 'revenue'])
    left, right = st.columns(2)
    with left:
        st.markdown(f"### Top {top_n} by {rank_by}")
        fig = px.bar(top.sort_values(key), x=key, y='item', orientation='h', color_discrete_sequence=['#E60012'],
                     hover_data=['category'])
        fig.update_yaxes(type='category')
        show_chart(fig, height=380, legend=False, x_title=rank_title, y_title="Item", money='x' if key == 'revenue' else None)
    with right:
        st.markdown(f"### Bottom {top_n} by {rank_by}")
        fig = px.bar(bottom.sort_values(key, ascending=False), x=key, y='item', orientation='h',
                     color_discrete_sequence=['#005BAC'], hover_data=['category'])
        fig.update_yaxes(type='category')
        show_chart(fig, height=380, legend=False, x_title=rank_title, y_title="Item", money='x' if key == 'revenue' else None)
        st.caption("Many items tie at the bottom (e.g. one unit sold), so this list is one of several valid answers.")

    left, right = st.columns([1, 1])
    with left:
        st.markdown("### Revenue Concentration (Pareto)")
        fig = go.Figure(go.Scatter(x=np.arange(1, len(t) + 1), y=t['cum_share'] * 100, line=dict(color='#E60012', width=3)))
        fig.add_hline(y=80, line_dash="dot", line_color="#333333")
        fig.update_xaxes(title="Items ranked by revenue")
        fig.update_yaxes(title="Cumulative % of revenue", ticksuffix="%")
        show_chart(fig, legend=False)
    with right:
        st.markdown("### Category Performance")
        cat = df_f.groupby('category', observed=True).agg(
            revenue=('sales', 'sum'), units=('qty', 'sum'), orders=('order', 'nunique'), items=('item', 'nunique'),
            gross=('gross', 'sum'), disc=('discount', 'sum')).reset_index().sort_values('revenue', ascending=False)
        cat['category'] = cat['category'].astype(str)
        cat['Share %'] = (cat['revenue'] / cat['revenue'].sum() * 100).round(1)
        cat['Avg discount %'] = np.where(cat['gross'] > 0, cat['disc'] / cat['gross'] * 100, np.nan).round(1)
        cat['revenue'] = cat['revenue'].round(0)
        cat['units'] = cat['units'].round(0)
        show_table(cat[['category', 'revenue', 'Share %', 'units', 'orders', 'items', 'Avg discount %']].rename(
            columns={'category': 'Category', 'revenue': 'Revenue', 'units': 'Units', 'orders': 'Orders', 'items': 'Items'}),
            height=380)

    with st.expander("Full item list (with ABC class)"):
        out = t[['item', 'category', 'production', 'abc', 'revenue', 'units', 'orders', 'customers', 'avg_price', 'disc_pct']].copy()
        out['category'] = out['category'].astype(str)
        out['production'] = out['production'].astype(str)
        out['disc_pct'] = (out['disc_pct'] * 100).round(1)
        out[['revenue', 'units', 'avg_price']] = out[['revenue', 'units', 'avg_price']].round(0)
        out.columns = ['Item', 'Category', 'Production status', 'ABC', 'Revenue', 'Units', 'Orders', 'Customers', 'Avg price', 'Discount %']
        show_table(out.head(1000))
        csv_button(out, "Download all items (CSV)", "products.csv")
