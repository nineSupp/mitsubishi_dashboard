"""Home = executive overview + four question cards that drill down into detail views."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from core.analytics import fy_revenue, growth_table, company_accuracy, complete_years
from core.context import kpis
from ui.model_panels import model_map
from ui.components import (kpi_card, show_chart, drill_chart, fmt_money, fmt_num, fmt_pct, pct_change, delta_badge,
                           drill_card, go as goto)


def _card_stats(ctx):
    """One headline number per question card (computed from the saved forecasts and the order history)."""
    s = {k: ("–", "Run `python -m scripts.train_forecasts` first") for k in ('forecast', 'inventory', 'accuracy')}
    o = ctx.outputs
    if o is not None:
        co = o['company']
        acc = company_accuracy(co)
        fy24 = ctx.df_all[(ctx.df_all['fy'] == 2024) & (ctx.df_all['status'] != 'Loss')]['sales'].sum()
        g = pct_change(co['forecast'].sum(), fy24)
        s['forecast'] = (fmt_money(co['forecast'].sum()), f"FY2025 forecast · {g * 100:+.1f}% vs FY2024")
        s['accuracy'] = (fmt_pct(acc['monthly'], 0),
                         f"FY2025 forecast vs real results · full-year total {acc['year_error'] * 100:+.1f}%")
        inv = o['inventory']
        n_dead = int((inv['flag'] == 'No sales 12+ months').sum())
        n_a = int((inv['abc'] == 'A').sum())
        s['inventory'] = (f"{n_dead:,} items", f"with no sales in 12+ months (as of Mar 2025) · {n_a:,} A-class items drive 80% of revenue")
    piv = fy_revenue(ctx.df_all, 'category', complete_years(ctx.df_all))
    gt = growth_table(piv, min_share=0.01).dropna(subset=['yoy'])
    if len(gt):
        best = gt['yoy'].idxmax()
        fys = sorted(piv.columns)
        s['growth'] = (f"{best} {gt.loc[best, 'yoy'] * 100:+.0f}%", f"fastest-growing category · FY{fys[-1]} vs FY{fys[-2]}")
    else:
        s['growth'] = ("–", "not enough history")
    return s


def render(ctx):
    d, dp = ctx.df_f, ctx.df_prev
    st.markdown("## Executive Overview")
    st.markdown("Performance snapshot for the current filters. Click a question below to dive into the details.")

    k = kpis(d)
    kp = kpis(dp) if dp is not None else None
    ch = lambda key, inv=False, fb="": delta_badge(  # noqa: E731
        pct_change(k[key], kp[key]) if kp else None, fb, inverse=inv)
    rev = d['sales'].sum()
    vip_share = d.loc[d['segment'] == 'VIP', 'sales'].sum() / rev if rev else np.nan
    top10 = d.groupby('customer', observed=True)['sales'].sum().nlargest(10).sum() / rev if rev else np.nan
    n_m = ctx.n_months

    c = st.columns(4)
    with c[0]:
        kpi_card("Total Revenue", fmt_money(k['revenue']), *ch('revenue', fb=f"≈ {fmt_money(k['revenue'] / n_m)} / month"))
    with c[1]:
        kpi_card("Orders", f"{k['orders']:,}", *ch('orders', fb=f"≈ {k['orders'] / n_m:,.0f} / month"))
    with c[2]:
        kpi_card("Active Customers", f"{k['customers']:,}", *ch('customers', fb="in selected period"))
    with c[3]:
        kpi_card("Avg Order Value", fmt_money(k['aov']), *ch('aov', fb="revenue ÷ orders"))
    st.markdown("<br>", unsafe_allow_html=True)
    c = st.columns(4)
    with c[0]:
        kpi_card("Units Sold", fmt_num(k['units']), *ch('units', fb=f"≈ {fmt_num(k['units'] / n_m)} / month"))
    with c[1]:
        kpi_card("Avg Discount", fmt_pct(k['disc']), *ch('disc', fb="of gross list value"))
    with c[2]:
        kpi_card("VIP Revenue Share", fmt_pct(vip_share), "share of revenue from VIP customers", "neutral")
    with c[3]:
        kpi_card("Top-10 Customer Share", fmt_pct(top10), "revenue concentration", "neutral")

    # ---- the four business questions (drill-down entry points) ----
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Business Questions")
    stats = _card_stats(ctx)
    cols = st.columns(4)
    with cols[0]:
        drill_card("Q1 · How much will we sell?", "Sales Forecast", *stats['forecast'], 'forecast')
    with cols[1]:
        drill_card("Q2 · What should we stock?", "Inventory Management", *stats['inventory'], 'inventory', tone="blue")
    with cols[2]:
        drill_card("Q3 · What is growing?", "Product & Category Growth", *stats['growth'], 'growth')
    with cols[3]:
        drill_card("Q4 · Can we trust it?", "Model Accuracy", *stats['accuracy'], 'accuracy', tone="blue")

    st.markdown("<br>", unsafe_allow_html=True)
    extra = st.columns(4)
    with extra[0]:
        drill_card("Plan · What if...?", "What-If Scenarios", "Test it", "price, discount, demand, lost customers, lead time", 'whatif')
    with extra[1]:
        drill_card("Extend · New data", "Add New Data", "Upload", "add orders, re-check and retrain the forecast", 'upload', tone="blue")
    with extra[2]:
        drill_card("Data · Raw files", "Import & Process Data", "Drop files", "raw Customer, Item and Sale Order files are cleaned for you", 'import')
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("More analysis")
    more = st.columns(4)
    for col, (view, label) in zip(more, [('products', 'Products'), ('customers', 'Customers'),
                                         ('industries', 'Industries'), ('orders', 'Orders')]):
        with col:
            st.button(label, key=f"more_{view}", on_click=goto, args=(view,), use_container_width=True)

    # ---- which model powers what ----
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Which model powers what")
    model_map(ctx.outputs['eval'] if ctx.outputs is not None else None)

    # ---- overview charts ----
    st.markdown("<br>", unsafe_allow_html=True)
    m = d.groupby('month').agg(revenue=('sales', 'sum'), discount=('discount', 'sum'), gross=('gross', 'sum')).reset_index()
    m['ma3'] = m['revenue'].rolling(3, min_periods=1).mean()
    m['disc_pct'] = np.where(m['gross'] > 0, m['discount'] / m['gross'], np.nan) * 100

    left, right = st.columns([2, 1])
    with left:
        st.markdown("### Monthly Revenue")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=m['month'], y=m['revenue'], name="Revenue", fill='tozeroy',
                                 line=dict(color='#E60012', width=2), fillcolor='rgba(230,0,18,0.12)'))
        fig.add_trace(go.Scatter(x=m['month'], y=m['ma3'], name="3-month average", line=dict(color='#005BAC', width=2, dash='dot')))
        show_chart(fig, x_title="Month", y_title=f"Revenue ({config.CURRENCY})", money='y')
    with right:
        st.markdown("### Share of Revenue by Product Category")
        cat = d.groupby('category', observed=True)['sales'].sum().sort_values(ascending=False)
        if len(cat) > 6:
            cat = pd.concat([cat.head(6), pd.Series({'Other categories': cat.iloc[6:].sum()})])
        fig = px.pie(names=cat.index.astype(str), values=cat.values, hole=0.6, color_discrete_sequence=config.BRAND_SEQ)
        fig.update_traces(textinfo='percent', textposition='inside', insidetextorientation='horizontal')
        fig.update_layout(uniformtext_minsize=11, uniformtext_mode='hide')
        show_chart(fig, legend=True, legend_pos='right')

    left, right = st.columns(2)
    with left:
        st.markdown("### Top 8 Industries by Revenue (click a bar to open Industries)")
        ind = d.groupby('industry', observed=True)['sales'].sum().nlargest(8).sort_values()
        fig = px.bar(x=ind.values, y=ind.index.astype(str), orientation='h', color_discrete_sequence=['#E60012'])
        drill_chart(fig, 'home_industry_bar', lambda pts, f: goto('industries'), legend=False,
                    x_title=f"Revenue ({config.CURRENCY})", y_title="Industry", money='x')
    with right:
        st.markdown("### Average Discount % by Month")
        fig = px.line(m, x='month', y='disc_pct', color_discrete_sequence=['#005BAC'])
        fig.update_yaxes(ticksuffix="%")
        show_chart(fig, legend=False, x_title="Month", y_title="Average discount (% of list value)")
