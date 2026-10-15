"""Q3: Growth of product categories and products by fiscal year (FY starts in April)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from core.analytics import fy_revenue, growth_table, item_growth, complete_years
from core.data import realised
from ui.model_panels import model_strip
from ui.components import back_bar, kpi_card, show_chart, drill_chart, show_table, csv_button, note, fmt_money, fmt_pct, go as goto


def _pick_cat(points, fig):
    """Click a bar (either chart) to drill into that category."""
    label = points[0].get('x') if fig.data[0].orientation != 'h' else points[0].get('y')
    if label in st.session_state.get('_gr_cats', []):
        st.session_state['gr_cat'] = label


def _drill_up():
    st.session_state['gr_cat'] = "All categories"


def render(ctx):
    back_bar('growth')
    st.markdown("## Product & Category Growth")
    st.markdown("Realised revenue by fiscal year (April to March), FY2021 to FY2024. Closed orders are excluded. "
                "FY2025 appears only as a forecast. The date-range filter does not apply here; the other sidebar filters do.")
    model_strip('growth', ctx)
    base = ctx.df_nd
    years = complete_years(ctx.df_all)
    partial = sorted(set(int(x) for x in ctx.df_all['fy'].unique()) - set(years))
    if partial:
        note(f"FY{', FY'.join(map(str, partial))} is not a full year yet, so it is left out of the growth figures.")
    piv = fy_revenue(base, 'category', years)
    fys = sorted(piv.columns)
    last, prev, first = fys[-1], fys[-2], fys[0]
    gt = growth_table(piv)
    gt_big = growth_table(piv, min_share=0.01).dropna(subset=['yoy'])

    total = piv.sum()
    c = st.columns(4)
    with c[0]:
        kpi_card(f"FY{last} Revenue", fmt_money(total[last]), f"{(total[last] / total[prev] - 1) * 100:+.1f}% vs FY{prev}",
                 "positive" if total[last] >= total[prev] else "negative")
    with c[1]:
        kpi_card(f"{last - first}-Year CAGR", fmt_pct((total[last] / total[first]) ** (1 / (last - first)) - 1),
                 f"FY{first} → FY{last}", "neutral")
    if len(gt_big):
        up, dn = gt_big['yoy'].idxmax(), gt_big['yoy'].idxmin()
        with c[2]:
            kpi_card("Fastest-growing category", up, f"{gt_big.loc[up, 'yoy'] * 100:+.1f}% vs FY{prev}", "positive")
        with c[3]:
            kpi_card("Biggest decline", dn, f"{gt_big.loc[dn, 'yoy'] * 100:+.1f}% vs FY{prev}", "negative")
    st.markdown("<br>", unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("### Revenue by fiscal year and category")
        top = piv[last].nlargest(8).index
        long = piv.loc[top].rename_axis('Category').reset_index().melt(
            id_vars='Category', var_name='Fiscal year', value_name='Revenue')
        long['Fiscal year'] = 'FY' + long['Fiscal year'].astype(str)
        fig = px.bar(long, x='Category', y='Revenue', color='Fiscal year', barmode='group', color_discrete_sequence=config.BRAND_SEQ)
        fig.update_yaxes(tickformat=".2s", title=None)
        drill_chart(fig, 'gr_fy_bar', _pick_cat, height=400, x_title="Product category", y_title=f"Revenue ({config.CURRENCY})", money='y')
    with right:
        st.markdown(f"### Growth FY{prev} → FY{last}")
        g = gt_big.sort_values('yoy')
        fig = go.Figure(go.Bar(x=g['yoy'] * 100, y=g.index, orientation='h',
                               marker_color=np.where(g['yoy'] >= 0, '#005BAC', '#E60012')))
        fig.update_xaxes(title="YoY %", ticksuffix="%")
        drill_chart(fig, 'gr_yoy_bar', _pick_cat, height=400, legend=False, x_title="Growth vs previous year (%)", y_title="Product category")

    # outlook next to history
    tbl = piv.copy()
    tbl.columns = [f"FY{c}" for c in tbl.columns]
    tbl['YoY %'] = (gt['yoy'] * 100).round(1)
    tbl['CAGR %'] = (gt['cagr'] * 100).round(1)
    if ctx.outputs is not None:
        oc = ctx.outputs['category']
        fo = oc.groupby('category')['forecast'].sum()
        tbl['FY2025 forecast'] = fo.reindex(tbl.index)
        tbl[f'Forecast vs FY{last} %'] = ((tbl['FY2025 forecast'] / tbl[f'FY{last}'] - 1) * 100).round(1)
    tbl = tbl.sort_values(f'FY{last}', ascending=False).reset_index().rename(columns={'index': 'Category', 'category': 'Category'})
    money_cols = [c for c in tbl.columns if c.startswith('FY') and not c.endswith('%')]
    tbl[money_cols] = tbl[money_cols].round(0)
    st.markdown("### Category growth table")
    show_table(tbl, height=420)
    csv_button(tbl, "Download category growth (CSV)", "category_growth.csv")

    # ---- level 2/3: drill into one category, then its items ----
    st.markdown("### Drill into a category")
    st.session_state['_gr_cats'] = list(tbl['Category'])
    cc1, cc2 = st.columns([3, 1])
    pick = cc1.selectbox("Category (or click a bar above)", ["All categories"] + list(tbl['Category']), key="gr_cat")
    if pick != "All categories":
        cc2.button("↑ Drill up to all categories", key="gr_up", on_click=_drill_up)
    r = realised(base)
    if pick != "All categories":
        r = r[r['category'].astype(str) == pick]
    by_fy = r.groupby('fy').agg(revenue=('sales', 'sum'), units=('qty', 'sum'), items=('item', 'nunique')).reset_index()
    left, right = st.columns(2)
    with left:
        fig = px.bar(by_fy, x=('FY' + by_fy['fy'].astype(str)), y='revenue', color_discrete_sequence=['#E60012'])
        show_chart(fig, height=300, legend=False, x_title="Fiscal year", y_title=f"Revenue ({config.CURRENCY})", money='y')
    with right:
        fig = px.bar(by_fy, x=('FY' + by_fy['fy'].astype(str)), y='units', color_discrete_sequence=['#005BAC'])
        show_chart(fig, height=300, legend=False, x_title="Fiscal year", y_title="Units sold")

    ig = item_growth(base, prev, last, pick, min_revenue=1.0)
    left, right = st.columns(2)
    for col, title, d in ((left, f"Top growing items (FY{prev} → FY{last})", ig.nlargest(10, 'change')),
                          (right, f"Top declining items (FY{prev} → FY{last})", ig.nsmallest(10, 'change'))):
        with col:
            st.markdown(f"### {title}")
            show_table(pd.DataFrame({"Item": d['item'], f"FY{prev}": d[prev].round(0), f"FY{last}": d[last].round(0),
                                     "Change": d['change'].round(0), "Change %": (d['change_pct'] * 100).round(1)}), height=380)
    st.button("Open full product performance →", key="more_products_from_growth", on_click=goto, args=('products',))
    note("Category names come from the item master in TNIC_Data_2025.xlsx. New items launched in a later year "
         "show up as growth in their category.")
