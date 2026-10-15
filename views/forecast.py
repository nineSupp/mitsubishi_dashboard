"""Q1: Sales forecast for FY2025 (trained on FY2021-FY2024 only).
Level 1 = company total, level 2 = category, level 3 = single item. Every level shows a low-high range.
The real FY2025 orders are NOT part of the data: they appear only when you switch on the comparison."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from core.data import realised
from ui.components import (back_bar, kpi_card, show_chart, drill_chart, show_table, csv_button, note,
                           fmt_money, fmt_num, fmt_pct, delta_badge, pct_change)
from ui.model_panels import model_strip
from views._guard import require_outputs

FY25_START = pd.Timestamp('2025-04-01')
NONE = "— none —"
CUR = config.CURRENCY


def _set_level(value):
    st.session_state['fc_level'] = value


def _set_item(value):
    st.session_state['fc_item'] = value


def _pick_category(points, fig):
    """Clicking a bar inside the chart drills into that category."""
    label = points[0].get('x')
    if label in st.session_state.get('_fc_cats', []):
        st.session_state['fc_level'] = label


def _pick_item(points, fig):
    """Clicking an item bar opens that item."""
    label = points[0].get('y')
    if label in st.session_state.get('_fc_items', []):
        st.session_state['fc_item'] = label


def _history(ctx, level, item=None):
    r = realised(ctx.df_all)
    if item:
        r = r[r['item'].astype(str) == item]
    elif level != 'Company total':
        r = r[r['category'].astype(str) == level]
    return r.groupby('month')['sales'].sum().reindex(ctx.all_months, fill_value=0.0)


def _coverage(f):
    d = f[(f['forecast'] > 0) & f['actual'].notna() & f['lo'].notna()]
    return float(((d['actual'] >= d['lo']) & (d['actual'] <= d['hi'])).mean()) if len(d) else np.nan


def _forecast_chart(hist, f, compare, title_y="Revenue"):
    fig = go.Figure()
    h = hist[hist.index < FY25_START]
    fig.add_trace(go.Scatter(x=h.index, y=h.values, name="Actual FY2021-FY2024", line=dict(color='#333333', width=2)))
    if f['lo'].notna().any():
        fig.add_trace(go.Scatter(x=f['month'], y=f['hi'], line=dict(width=0), showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=f['month'], y=f['lo'], line=dict(width=0), fill='tonexty',
                                 fillcolor='rgba(230,0,18,0.15)', name="Low-high range (~80%)", hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=f['month'], y=f['forecast'], name="Forecast FY2025", mode='lines+markers',
                             line=dict(color='#E60012', width=3)))
    if compare:
        fig.add_trace(go.Scatter(x=f['month'], y=f['actual'], name="Real FY2025", line=dict(color='#005BAC', width=2.5, dash='dot')))
    return fig


def render(ctx):
    back_bar('forecast')
    st.markdown("## Sales Forecast: FY2025")
    st.markdown("Forecast for April 2025 to March 2026, made from FY2021-FY2024 data only. "
                "Every level shows the expected value plus a low and high range.")
    model_strip('forecast', ctx)
    if not require_outputs(ctx):
        return
    o = ctx.outputs

    c1, c2 = st.columns([3, 2])
    cats = sorted(o['category']['category'].unique())
    st.session_state['_fc_cats'] = cats
    level = c2.selectbox("Level (drill down)", ["Company total"] + cats, key="fc_level")
    if level != 'Company total':
        c2.button("↑ Drill up to company total", key="fc_up", on_click=_set_level, args=('Company total',))
    compare = c1.toggle("Compare with the real FY2025 results (TNIC_Data_2025.xlsx)", value=False, key="fc_compare")

    # reset the chosen item whenever the level changes
    if st.session_state.get('_fc_prev_level') != level:
        st.session_state['fc_item'] = NONE
        st.session_state['_fc_prev_level'] = level

    # ---- items available at this level (top 25 by forecast revenue) ----
    it_all = o['item'] if level == 'Company total' else o['item'][o['item']['category'] == level]
    g_items = (it_all.groupby(['item', 'category'], as_index=False)[['forecast', 'forecast_qty', 'actual', 'actual_qty']]
               .sum(min_count=1).sort_values('forecast', ascending=False).head(25))
    item_names = list(g_items['item'].astype(str))
    st.session_state['_fc_items'] = item_names
    if st.session_state.get('fc_item') not in [NONE] + item_names:
        st.session_state['fc_item'] = NONE
    item = st.session_state.get('fc_item', NONE)
    item = None if item == NONE else item

    # ---- the series being shown: company, category or item ----
    if item:
        f = it_all[it_all['item'].astype(str) == item].sort_values('month').reset_index(drop=True)
        label = f"Item {item}"
    elif level == 'Company total':
        f = o['company'].sort_values('month').reset_index(drop=True)
        label = "Company total"
    else:
        f = o['category'][o['category']['category'] == level].sort_values('month').reset_index(drop=True)
        label = level
    hist = _history(ctx, level, item)
    fy24 = hist[hist.index >= pd.Timestamp('2024-04-01')].sum()
    fc_total = f['forecast'].sum()
    peak = f.loc[f['forecast'].idxmax()]

    cols = st.columns(4)
    with cols[0]:
        kpi_card("Forecast FY2025", fmt_money(fc_total), label, "neutral")
    with cols[1]:
        kpi_card("Actual FY2024 (training data)", fmt_money(fy24), "last year in the data", "neutral")
    g = pct_change(fc_total, fy24)
    with cols[2]:
        text, _ = delta_badge(g, "", note="vs FY2024")
        kpi_card("Expected growth", fmt_pct(g), text, "neutral")
    with cols[3]:
        kpi_card("Peak month", peak['month'].strftime("%b %Y"), fmt_money(peak['forecast']), "neutral")
    if compare:
        st.markdown("<br>", unsafe_allow_html=True)
        a_tot = f['actual'].sum()
        err = pct_change(fc_total, a_tot)
        acc = max(1 - np.abs(f['actual'] - f['forecast']).sum() / max(np.abs(f['actual']).sum(), 1e-9), 0)
        cols = st.columns(4)
        with cols[0]:
            kpi_card("Real FY2025 result", fmt_money(a_tot), "from TNIC_Data_2025.xlsx", "neutral")
        with cols[1]:
            text, tone = delta_badge(err, "", note="forecast vs real")
            kpi_card("Full-year error", fmt_pct(err), text, tone)
        with cols[2]:
            kpi_card("Monthly accuracy", fmt_pct(acc, 0), "1 − WAPE across 12 months", "neutral")
        with cols[3]:
            cov = _coverage(f)
            kpi_card("Months inside the range", fmt_pct(cov, 0) if not np.isnan(cov) else "–", "real value between low and high (target ≈ 80%)", "neutral")
    st.markdown("<br>", unsafe_allow_html=True)

    # ---- main chart: history, forecast and low-high range ----
    st.markdown(f"### {label}: history and FY2025 forecast (revenue)")
    if item:
        st.button("↑ Drill up to category view", key="fc_item_up", on_click=_set_item, args=(NONE,))
    fig = _forecast_chart(hist, f, compare)
    show_chart(fig, height=400, x_title="Month", y_title=f"Revenue ({CUR})", money='y')
    if level != 'Company total' or item:
        what = ("This item's typical month-to-month swing (10th to 90th percentile of its own monthly sales over the last 24 months)"
                if item else "The range is the 10th to 90th percentile of how far past category forecasts were from reality")
        st.caption(f"{what}. It shows how high or low a month could plausibly land.")

    left, right = st.columns(2)
    with left:
        st.markdown("### Monthly Table")
        tbl = pd.DataFrame({"Month": f['month'].dt.strftime("%b %Y"), "Forecast": f['forecast'].round(0),
                            "Low (~80%)": f['lo'].round(0), "High (~80%)": f['hi'].round(0)})
        if item:
            tbl["Forecast units"], tbl["Low units"], tbl["High units"] = f['forecast_qty'].round(1), f['lo_qty'].round(1), f['hi_qty'].round(1)
        if compare:
            tbl["Real"] = f['actual'].round(0)
            tbl["Error %"] = np.where(f['actual'] > 0, (f['forecast'] / f['actual'] - 1) * 100, np.nan).round(1)
            tbl["Inside range"] = np.where(f['actual'].between(f['lo'], f['hi']), "yes", "no")
        show_table(tbl)
        csv_button(tbl, "Download this table (CSV)", "sales_forecast_fy2025.csv")
    with right:
        if item:
            st.markdown("### Item details")
            row = g_items[g_items['item'].astype(str) == item].iloc[0]
            last12 = hist[hist.index >= pd.Timestamp('2024-04-01')]
            show_table(pd.DataFrame({
                "Measure": ["Category", "Forecast units FY2025", f"Forecast revenue FY2025 ({CUR})", f"Actual revenue FY2024 ({CUR})", "Months with sales in FY2024"],
                "Value": [row['category'], f"{row['forecast_qty']:,.1f}", f"{row['forecast']:,.0f}", f"{last12.sum():,.0f}", f"{int((last12 > 0).sum())} of 12"]}))
        elif level == 'Company total':
            st.markdown("### By Category")
            cc = o['category'].groupby('category')[['forecast', 'actual']].sum().sort_values('forecast', ascending=False).head(10)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=cc.index, y=cc['forecast'], name="Forecast", marker_color='#E60012'))
            if compare:
                fig.add_trace(go.Bar(x=cc.index, y=cc['actual'], name="Real FY2025", marker_color='#005BAC'))
            fig.update_layout(barmode='group')
            drill_chart(fig, 'fc_cat_bar', _pick_category, height=380, x_title="Product category",
                        y_title=f"Revenue FY2025 ({CUR})", money='y')
        else:
            st.markdown("### Seasonality across years")
            sd = hist.reset_index()
            sd.columns = ['month', 'value']
            sd['Year'] = sd['month'].dt.year.astype(str)
            sd['Month'] = sd['month'].dt.month
            fig = px.line(sd, x='Month', y='value', color='Year', markers=True, color_discrete_sequence=config.BRAND_SEQ)
            show_chart(fig, height=380, x_title="Calendar month (1 = January)", y_title=f"Revenue ({CUR})", money='y')

    # ---- level 3: items (click a bar to open one) ----
    if not item:
        st.markdown("### Items behind this forecast (click a bar to open an item)")
        top10 = g_items.head(10).sort_values('forecast')
        fig = go.Figure(go.Bar(x=top10['forecast'], y=top10['item'].astype(str), orientation='h', marker_color='#E60012',
                               name="Forecast FY2025"))
        if compare:
            real = top10['actual']
            fig.add_trace(go.Bar(x=real, y=top10['item'].astype(str), orientation='h', marker_color='#005BAC', name="Real FY2025"))
            fig.update_layout(barmode='group')
        fig.update_yaxes(type='category')
        drill_chart(fig, 'fc_item_bar', _pick_item, height=420, legend=compare,
                    x_title=f"Revenue FY2025 ({CUR})", y_title="Item", money='x')
    pick = st.selectbox("Item (or click a bar above)", [NONE] + item_names, key="fc_item")
    out = pd.DataFrame({"Item": g_items['item'], "Category": g_items['category'],
                        "Forecast revenue": g_items['forecast'].round(0), "Forecast units": g_items['forecast_qty'].round(1)})
    if compare:
        out["Real revenue"] = g_items['actual'].round(0)
        out["Real units"] = g_items['actual_qty'].round(0)
    show_table(out, height=380)
    csv_button(out, "Download item forecast (CSV)", "item_forecast_fy2025.csv")

    note("<b>Training and testing.</b> Models were validated on FY2023 and FY2024 using only earlier years, then trained on "
         "FY2021-FY2024 to forecast FY2025. The real FY2025 orders are used only for the comparison switch above and the "
         "Model Accuracy page. Closed orders are excluded. Forecasts ignore the sidebar filters. Amounts are in Thai Baht (฿).")
