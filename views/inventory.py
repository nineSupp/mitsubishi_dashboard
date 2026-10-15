"""Q2: Inventory management. Demand-based planning (the data has sales orders, not stock levels)."""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import config
from forecasting.planning import plan_reorder
from ui.components import back_bar, kpi_card, show_chart, drill_chart, show_table, csv_button, note, fmt_money, fmt_num, fmt_pct
from ui.model_panels import model_strip
from views._guard import require_outputs

POLICY = pd.DataFrame({
    "Class": ["A-X", "A-Y", "A-Z", "B-X / B-Y", "B-Z", "C-X / C-Y", "C-Z"],
    "Meaning": ["High value, steady demand", "High value, moderate swings", "High value, erratic demand",
                "Medium value", "Medium value, erratic", "Low value", "Low value, erratic or rare"],
    "Suggested policy": ["Continuous replenishment, tight safety stock", "Regular review, standard safety stock",
                         "Higher safety stock or order against confirmed demand", "Periodic review (monthly)",
                         "Order against demand, small buffer", "Min/max rule, review quarterly",
                         "Do not stock deep; make-to-order or clear"],
})


SEGMENTS = ["All", "A-X", "A-Y", "A-Z", "B-X", "B-Y", "B-Z", "C-X", "C-Y", "C-Z"]
FLAG_ORDER = ['No sales 12+ months', 'Slow-moving (6-11 months)', "Discontinued/TBA but still selling", 'Healthy']


def _pick_segment(points, fig):
    """Click a bubble in the ABC x XYZ matrix to open that segment."""
    p = points[0]
    seg = f"{p.get('y')}-{p.get('x')}"
    if seg in SEGMENTS:
        st.session_state['inv_segment'] = seg


def _pick_flag_category(points, fig):
    """Click a bar segment (category x flag) to open that group for that category."""
    p = points[0]
    try:
        name = fig.data[p.get('curve_number', 0)].name
    except Exception:
        name = None
    if name in FLAG_ORDER[:3]:
        st.session_state['inv_flag'] = name
    if p.get('x'):
        st.session_state['inv_flag_cat'] = p['x']


def _pick_flag(points, fig):
    label = points[0].get('x')
    if label in FLAG_ORDER[:3]:
        st.session_state['inv_flag'] = label
        st.session_state['inv_flag_cat'] = 'All categories'


def _reset(**values):
    for k, v in values.items():
        st.session_state[k] = v


def render(ctx):
    back_bar('inventory')
    st.markdown("## Inventory Management")
    st.markdown("Which items deserve stock, how much buffer to hold, and which items are tying up money. "
                "Planning date: end of March 2025 (FY2021-FY2024 data only); the demand forecast covers FY2025.")
    model_strip('inventory', ctx)
    if not require_outputs(ctx):
        return
    inv = ctx.outputs['inventory']

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Priorities (ABC × XYZ)", "Reorder planner", "Slow & dead stock",
                                            "Stock on hand", "Back-check vs real FY2025"])

    # ------------------------------------------------------------------ priorities
    with tab1:
        active = inv[inv['revenue_12m'] > 0]
        c = st.columns(4)
        with c[0]:
            kpi_card("Active items (12 mo)", f"{len(active):,}", f"of {len(inv):,} items ever sold", "neutral")
        with c[1]:
            a = active[active['abc'] == 'A']
            kpi_card("A-class items", f"{len(a):,}", f"{fmt_pct(a['revenue_12m'].sum() / active['revenue_12m'].sum(), 0)} of revenue", "neutral")
        with c[2]:
            az = active[(active['abc'] == 'A') & (active['xyz'] == 'Z')]
            kpi_card("A-Z items (watch list)", f"{len(az):,}", "high value but erratic demand", "negative")
        with c[3]:
            kpi_card("Items with erratic demand", f"{int((active['xyz'] == 'Z').sum()):,}", "variability high or <3 active months", "neutral")
        st.markdown("<br>", unsafe_allow_html=True)

        left, right = st.columns([2, 3])
        with left:
            st.markdown("### Item count: value class × demand pattern")
            m = active.groupby(['abc', 'xyz']).size().unstack(fill_value=0).reindex(index=['A', 'B', 'C'], columns=['X', 'Y', 'Z'], fill_value=0)
            long = m.stack().reset_index()
            long.columns = ['abc', 'xyz', 'items']
            fig = px.scatter(long, x='xyz', y='abc', size='items', color='items', text='items', size_max=55,
                             color_continuous_scale=['#F26B76', '#B3001B'], category_orders={'xyz': ['X', 'Y', 'Z'], 'abc': ['C', 'B', 'A']})
            fig.update_traces(textposition='middle center', textfont=dict(color='#FFFFFF'))
            fig.update_xaxes(title="Demand pattern (X steady → Z erratic)")
            fig.update_yaxes(title="Value class")
            fig.update_coloraxes(showscale=False)
            drill_chart(fig, 'inv_matrix', _pick_segment, height=300, legend=False)
        with right:
            st.markdown("### Suggested policy per class")
            show_table(POLICY, height=300)
        sc1, sc2 = st.columns([3, 1])
        seg = sc1.selectbox("Open a segment (or click a bubble above)", SEGMENTS, key="inv_segment")
        if seg != "All":
            sc2.button("↑ Drill up to all items", key="inv_seg_up", on_click=_reset, kwargs=dict(inv_segment="All"))
        v = active if seg == "All" else active[(active['abc'] == seg[0]) & (active['xyz'] == seg[2])]
        out = v.sort_values('revenue_12m', ascending=False).head(300)
        show_table(pd.DataFrame({"Item": out['item'], "Category": out['category'], "ABC": out['abc'], "XYZ": out['xyz'],
                                 "Revenue 12m": out['revenue_12m'].round(0), "Units 12m": out['qty_12m'].round(0),
                                 "Avg monthly units": out['avg_monthly_qty'].round(2), "Months since last sale": out['months_since_last_sale']}), height=360)

    # ------------------------------------------------------------------ reorder planner
    with tab2:
        c1, c2, c3 = st.columns(3)
        lead = c1.slider("Supplier lead time (months)", 0.5, 6.0, 2.0, 0.5, key="inv_lead")
        service = c2.selectbox("Target service level", [0.90, 0.95, 0.975, 0.99], index=1, format_func=lambda x: f"{x:.1%}", key="inv_sl")
        horizon = c3.radio("Demand basis (next months)", [3, 6, 12], index=0, horizontal=True, key="inv_h")
        p = plan_reorder(inv[inv['revenue_12m'] > 0], lead, service, horizon)
        f1, f2 = st.columns(2)
        cat_pick = f1.multiselect("Category (all if empty)", sorted(p['category'].unique()), key="inv_cat")
        abc_pick = f2.multiselect("ABC class (all if empty)", ['A', 'B', 'C'], default=['A'], key="inv_abc")
        if cat_pick:
            p = p[p['category'].isin(cat_pick)]
        if abc_pick:
            p = p[p['abc'].isin(abc_pick)]
        p = p.sort_values('revenue_12m', ascending=False)
        c = st.columns(3)
        with c[0]:
            kpi_card("Items in plan", f"{len(p):,}", f"lead time {lead:g} mo · service {service:.1%}", "neutral")
        with c[1]:
            kpi_card("Total safety stock", fmt_num(p['safety'].sum()), "units across listed items", "neutral")
        with c[2]:
            kpi_card("Value of safety stock", fmt_money((p['safety'] * p['avg_unit_price'].fillna(0)).sum()), "at recent average price", "neutral")
        st.markdown("<br>", unsafe_allow_html=True)
        out = pd.DataFrame({"Item": p['item'], "Category": p['category'], "ABC": p['abc'], "XYZ": p['xyz'],
                            "Forecast units / month": p['mu'].round(2), "Std dev / month": p['std_monthly_qty'].round(2),
                            "Safety stock": p['safety'], "Reorder point": p['rop'],
                            "Avg unit price": p['avg_unit_price'].round(0), "Months since last sale": p['months_since_last_sale']})
        show_table(out.head(500), height=420)
        csv_button(out, "Download reorder plan (CSV)", "reorder_plan.csv")
        note("Safety stock = z × monthly standard deviation × √lead time. Reorder point = forecast demand during lead time "
             "+ safety stock. Standard deviation comes from the last 12 months (one-off bulk orders are capped). "
             "Lead time and service level are your assumptions, because the data has no supplier lead times.")

    # ------------------------------------------------------------------ slow & dead
    with tab3:
        order = ['No sales 12+ months', 'Slow-moving (6-11 months)', "Discontinued/TBA but still selling", 'Healthy']
        cnt = inv['flag'].value_counts().reindex(order, fill_value=0)
        c = st.columns(4)
        for col, name in zip(c, order):
            with col:
                kpi_card(name, f"{int(cnt[name]):,}", f"{fmt_pct(cnt[name] / len(inv), 0)} of items",
                         "negative" if name != 'Healthy' else "positive")
        st.markdown("<br>", unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.markdown("### Items by stock health, per category")
            g = inv[inv['flag'] != 'Healthy'].groupby(['category', 'flag']).size().reset_index(name='items')
            top = g.groupby('category')['items'].sum().nlargest(10).index
            fig = px.bar(g[g['category'].isin(top)], x='category', y='items', color='flag',
                         color_discrete_sequence=['#E60012', '#F26B76', '#005BAC'])
            drill_chart(fig, 'inv_flag_cat_bar', _pick_flag_category, height=360, x_title="Product category", y_title="Number of items")
        with right:
            st.markdown("### Revenue of these items in the last 12 months")
            r = inv.groupby('flag')['revenue_12m'].sum().reindex(order, fill_value=0)
            fig = px.bar(x=r.index, y=r.values, color_discrete_sequence=['#6C757D'])
            drill_chart(fig, 'inv_flag_bar', _pick_flag, height=360, legend=False,
                        x_title="Stock-health group", y_title=f"Revenue in the last 12 months ({config.CURRENCY})", money='y')
        f1, f2, f3 = st.columns([2, 2, 1])
        pick = f1.selectbox("Open a group (or click a bar above)", order[:3], key="inv_flag")
        cats_here = ["All categories"] + sorted(inv['category'].unique())
        cat_pick = f2.selectbox("Category", cats_here, key="inv_flag_cat")
        if cat_pick != "All categories":
            f3.button("↑ All categories", key="inv_flag_up", on_click=_reset, kwargs=dict(inv_flag_cat="All categories"))
        v = inv[inv['flag'] == pick]
        if cat_pick != "All categories":
            v = v[v['category'] == cat_pick]
        v = v.sort_values(['months_since_last_sale', 'qty_12m'], ascending=[False, False]).head(500)
        out = pd.DataFrame({"Item": v['item'], "Category": v['category'], "Production status": v['production'],
                            "Last sale": v['last_sale'].dt.strftime("%b %Y"), "Months since last sale": v['months_since_last_sale'],
                            "Units 12m": v['qty_12m'].round(0), "Avg unit price": v['avg_unit_price'].round(0)})
        show_table(out, height=380)
        csv_button(out, "Download this list (CSV)", "slow_dead_stock.csv")
        note("There is no product launch date in the data and history starts in April 2021, so true product age "
             "(for example older than 5 years) cannot be measured. Months since last sale is used as the closest "
             "signal of ageing stock. Add stock-on-hand in the next tab to turn this into money at risk.")

    # ------------------------------------------------------------------ stock on hand (optional)
    with tab4:
        st.markdown("Upload current stock to see cover, excess and shortage risk. "
                    "CSV with two columns: `item` (item code) and `on_hand` (units).")
        template = pd.DataFrame({"item": inv['item'].head(5), "on_hand": [0] * 5})
        csv_button(template, "Download template", "stock_on_hand_template.csv")
        path = config.DATA_DIR / "stock_on_hand.csv"
        up = st.file_uploader("Stock on hand (CSV)", type="csv", key="inv_upload")
        stock = None
        if up is not None:
            stock = pd.read_csv(up)
        elif path.exists():
            stock = pd.read_csv(path)
            st.caption(f"Using {path.name} from the data folder.")
        if stock is None or not {'item', 'on_hand'} <= set(stock.columns):
            st.info("No stock file yet. Everything above works without it.")
        else:
            stock['item'] = stock['item'].astype(str)
            m = inv.merge(stock[['item', 'on_hand']], on='item', how='inner')
            lead_s = st.session_state.get('inv_lead', 2.0)
            m['mu'] = m['fc_qty_next12'] / 12
            m['cover'] = np.where(m['mu'] > 0, m['on_hand'] / m['mu'], np.inf)
            m['excess_units'] = np.maximum(m['on_hand'] - m['fc_qty_next12'], 0)
            m['excess_value'] = m['excess_units'] * m['avg_unit_price'].fillna(0)
            m['below_rop'] = m['on_hand'] < (m['mu'] * lead_s)
            c = st.columns(4)
            with c[0]:
                kpi_card("Items matched", f"{len(m):,}", f"of {len(stock):,} rows", "neutral")
            with c[1]:
                kpi_card("Stock value", fmt_money((m['on_hand'] * m['avg_unit_price'].fillna(0)).sum()), "at recent average price", "neutral")
            with c[2]:
                kpi_card("Excess vs 12-mo demand", fmt_money(m['excess_value'].sum()), "money tied up beyond a year of demand", "negative")
            with c[3]:
                kpi_card("Short of lead-time demand", f"{int(m['below_rop'].sum()):,}", f"lead time {lead_s:g} mo", "negative")
            out = pd.DataFrame({"Item": m['item'], "Category": m['category'], "ABC": m['abc'], "On hand": m['on_hand'],
                                "Forecast / month": m['mu'].round(2), "Months of cover": m['cover'].replace(np.inf, np.nan).round(1),
                                "Excess units": m['excess_units'].round(0), "Excess value": m['excess_value'].round(0),
                                "Flag": m['flag']}).sort_values('Excess value', ascending=False)
            show_table(out.head(500), height=400)
            csv_button(out, "Download stock review (CSV)", "stock_review.csv")

    # ------------------------------------------------------------------ back-check (comparison only)
    with tab5:
        st.markdown("Comparison only: the plan above was made with data up to March 2025. Here it is checked against the "
                    "real FY2025 orders from TNIC_Data_2025.xlsx, which were never used to build it.")
        bc = inv.copy()
        bc['sold_fy25'] = bc['actual_fy25_qty'] > 0
        order = ['No sales 12+ months', 'Slow-moving (6-11 months)', "Discontinued/TBA but still selling", 'Healthy']
        fl = bc.groupby('flag').agg(items=('item', 'count'), sold=('sold_fy25', 'sum'),
                                    real_rev=('actual_fy25_revenue', 'sum')).reindex(order).fillna(0)
        fl['pct'] = np.where(fl['items'] > 0, fl['sold'] / fl['items'], np.nan)
        c = st.columns(3)
        with c[0]:
            d = fl.loc['No sales 12+ months']
            kpi_card("Dead-stock flags that stayed dead", fmt_pct(1 - d['pct'], 0), f"{int(d['items']):,} items flagged, {int(d['sold']):,} sold in FY2025", "positive")
        with c[1]:
            kpi_card("Real FY2025 revenue of flagged-dead items", fmt_money(d['real_rev']), "money they still brought in", "neutral")
        a = bc[bc['abc'] == 'A']
        wape = np.abs(a['actual_fy25_qty'] - a['fc_qty_next12']).sum() / max(a['actual_fy25_qty'].sum(), 1e-9)
        with c[2]:
            kpi_card("A-class demand accuracy (units)", fmt_pct(max(1 - wape, 0), 0), "forecast vs real FY2025 units per item", "neutral")
        st.markdown("<br>", unsafe_allow_html=True)
        left, right = st.columns(2)
        with left:
            st.markdown("### Did each flag group really stop selling?")
            show_table(pd.DataFrame({"Flag": fl.index, "Items": fl['items'].astype(int), "Sold in FY2025": fl['sold'].astype(int),
                                     "% that sold": (fl['pct'] * 100).round(1), "Real FY2025 revenue": fl['real_rev'].round(0)}))
        with right:
            st.markdown("### Demand forecast vs real units, by ABC class")
            rows = []
            for k in ('A', 'B', 'C'):
                x = bc[bc['abc'] == k]
                den = max(x['actual_fy25_qty'].sum(), 1e-9)
                rows.append({"Class": k, "Items": len(x), "Forecast units": round(x['fc_qty_next12'].sum()),
                             "Real units": round(x['actual_fy25_qty'].sum()),
                             "Item-level accuracy %": round(max(1 - np.abs(x['actual_fy25_qty'] - x['fc_qty_next12']).sum() / den, 0) * 100, 1)})
            show_table(pd.DataFrame(rows))
        note("Flagged-dead items can still sell a little (one-off orders), so a flag means 'do not restock deep', not 'worthless'. "
             "Item-level demand is hard to forecast; use safety stock rather than exact numbers.")
