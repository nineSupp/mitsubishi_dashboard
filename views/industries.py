"""Industries view (ported from main_dashboard.py; logic unchanged, now reads from the shared AppContext)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import BRAND_SEQ, WEEKDAYS, CURRENCY
from ui.model_panels import model_strip
from ui.components import back_bar, kpi_card, show_chart, show_table, csv_button, fmt_num, fmt_money, fmt_pct


def render(ctx):
    df_f, f_end, N_MONTHS = ctx.df_f, ctx.f_end, ctx.n_months
    back_bar('industries')
    model_strip('industries', ctx)
    st.markdown("## Industries")
    st.markdown("Revenue by customer industry. The dataset has no geographic column, so a region map is not possible yet.")
    top_n = 12
    ind = df_f.groupby('industry', observed=True).agg(
        revenue=('sales', 'sum'), customers=('customer', 'nunique'), orders=('order', 'nunique'),
        gross=('gross', 'sum'), disc=('discount', 'sum')).reset_index().sort_values('revenue', ascending=False)
    ind['industry'] = ind['industry'].astype(str)
    ind['share'] = ind['revenue'] / ind['revenue'].sum() * 100
    ind['aov'] = np.where(ind['orders'] > 0, ind['revenue'] / ind['orders'], np.nan)
    ind['disc_pct'] = np.where(ind['gross'] > 0, ind['disc'] / ind['gross'] * 100, np.nan)

    top = ind.head(1).iloc[0]
    c = st.columns(3)
    with c[0]:
        kpi_card("Industries", f"{len(ind):,}", "with sales in selection", "neutral")
    with c[1]:
        kpi_card("Largest Industry", top['industry'], f"{top['share']:.1f}% of revenue", "neutral")
    with c[2]:
        kpi_card("Top-3 Industry Share", fmt_pct(ind['share'].head(3).sum() / 100), "revenue concentration", "neutral")
    st.markdown("<br>", unsafe_allow_html=True)

    keep = ind['industry'].head(top_n).tolist()
    tm = df_f.assign(industry_g=np.where(df_f['industry'].astype(str).isin(keep), df_f['industry'].astype(str), 'All other industries'))
    tm = tm.groupby(['industry_g', 'category'], observed=True)['sales'].sum().reset_index()
    tm = tm[tm['sales'] > 0]
    tm['category'] = tm['category'].astype(str)

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"### Revenue Treemap: Industry → Product Category")
        fig = px.treemap(tm, path=[px.Constant("All industries"), 'industry_g', 'category'], values='sales',
                         color_discrete_sequence=BRAND_SEQ)
        fig.update_traces(root_color="#F8F9FA")
        show_chart(fig, height=440, legend=False)
    with right:
        st.markdown("### Industry Table")
        out = pd.DataFrame({
            'Industry': ind['industry'], 'Revenue': ind['revenue'].round(0), 'Share %': ind['share'].round(1),
            'Customers': ind['customers'], 'Orders': ind['orders'], 'Avg order value': ind['aov'].round(0),
            'Avg discount %': ind['disc_pct'].round(1)})
        show_table(out, height=440)
        csv_button(out, "Download industries (CSV)", "industries.csv")

    st.markdown(f"### Heatmap: Top {top_n} Industries × Product Category (revenue)")
    hm = df_f[df_f['industry'].astype(str).isin(keep)].groupby(['industry', 'category'], observed=True)['sales'].sum().reset_index()
    hm['industry'] = hm['industry'].astype(str)
    hm['category'] = hm['category'].astype(str)
    pivot = hm.pivot_table(index='industry', columns='category', values='sales', aggfunc='sum', fill_value=0)
    pivot = pivot.loc[[i for i in keep if i in pivot.index]]
    fig = px.imshow(pivot.values, x=list(pivot.columns), y=list(pivot.index), aspect='auto',
                    color_continuous_scale=['#FFFFFF', '#F26B76', '#E60012'])
    fig.update_layout(coloraxis_colorbar_title_text=f"Revenue ({CURRENCY})")
    show_chart(fig, height=420, legend=False, x_title="Product category", y_title="Industry")
