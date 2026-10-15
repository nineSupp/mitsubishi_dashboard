"""What-If Scenarios: change assumptions and see revenue, units and inventory react."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from core.data import realised
from forecasting.planning import plan_reorder
from forecasting.scenario import run_scenario
from ui.components import (back_bar, kpi_card, show_chart, show_table, csv_button, note,
                           fmt_money, fmt_num, fmt_pct, delta_badge, pct_change)
from ui.model_panels import model_strip
from views._guard import require_outputs

DEFAULTS = dict(wi_demand=0, wi_price=0, wi_disc=0, wi_elast=-1.0, wi_topn=0, wi_lostpct=100, wi_new=0)
PRESETS = {
    "Custom (use the sliders)": None,
    "Demand shock like FY2023 (−30%)": dict(wi_demand=-30),
    "Price +5%, customers react strongly (elasticity −2)": dict(wi_price=5, wi_elast=-2.0),
    "Discount push: +5 points of discount": dict(wi_disc=5, wi_elast=-1.5),
    "Lose the top 3 customers": dict(wi_topn=3, wi_lostpct=100),
    "New product launches add 5% revenue": dict(wi_new=5),
}


def _apply_preset():
    """Runs before the page reruns, so it may set the slider values."""
    vals = PRESETS.get(st.session_state.get('wi_preset'))
    if vals is None:
        return
    for k, v in {**DEFAULTS, **vals}.items():
        st.session_state[k] = v


def _reset_all():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.session_state['wi_preset'] = list(PRESETS)[0]


def _baselines(o):
    b = {"FY2025 forecast (validated)": (o['company'], o['category'], o['inventory'])}
    u = o.get('updated')
    if u:
        b["Updated forecast (history + your added data)"] = (u['company'], u['category'], u['inventory'])
    return b


def render(ctx):
    back_bar('whatif')
    st.markdown("## What-If Scenarios")
    st.markdown("Change the assumptions and see what happens to revenue, units and inventory. "
                "Results are arithmetic on the baseline forecast, driven by your assumptions.")
    model_strip('whatif', ctx)
    if not require_outputs(ctx):
        return
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(k, v)
    bases = _baselines(ctx.outputs)
    names = list(bases)
    base_name = st.radio("Baseline", names, horizontal=True, key="wi_base") if len(names) > 1 else names[0]
    comp, cat, inv = bases[base_name]
    tab_s, tab_i = st.tabs(["Sales & revenue", "Inventory"])

    # =============================================================== sales
    with tab_s:
        pc1, pc2 = st.columns([3, 1])
        pc1.selectbox("Start from a preset", list(PRESETS), key="wi_preset", on_change=_apply_preset)
        pc2.button("Reset all", key="wi_reset", on_click=_reset_all)

        r24 = realised(ctx.df_all)
        r24 = r24[r24['fy'] == 2024]
        gross, disc = r24['gross'].sum(), r24['discount'].sum()
        base_disc = float(disc / gross) if gross else 0.0

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Market**")
            st.slider("Demand change (%)", -40, 40, key="wi_demand", help="Applies to the chosen categories (all if none chosen).")
            st.slider("New-item revenue (% of baseline)", 0, 15, key="wi_new",
                      help="Brand-new products have no list price yet, so the cleaning rules leave them out of the data (about ฿108M of FY2025 orders). Use this lever to add them back as an assumption.")
        with c2:
            st.markdown("**Price and discount**")
            st.slider("List price change (%)", -20, 20, key="wi_price")
            st.slider("Extra discount (percentage points)", -10, 15, key="wi_disc",
                      help=f"Average discount in FY2024 was {base_disc * 100:.1f}% of list value.")
            st.slider("Price elasticity (volume response)", -3.0, 0.0, step=0.1, key="wi_elast",
                      help="−1.0 means a 1% higher net price loses about 1% of units. It is an assumption, not measured from the data.")
        with c3:
            st.markdown("**Customers and scope**")
            st.slider("Top customers lost (number)", 0, 25, key="wi_topn", help="Ranked by FY2024 revenue.")
            st.slider("Share of their business lost (%)", 0, 100, key="wi_lostpct")
            cats_sel = st.multiselect("Apply to categories (all if empty)", sorted(cat['category'].unique()), key="wi_cats")

        sub = r24 if not cats_sel else r24[r24['category'].astype(str).isin(cats_sel)]
        by_cust = sub.groupby('customer', observed=True)['sales'].sum()
        lost_share = float(by_cust.nlargest(int(st.session_state['wi_topn'])).sum() / by_cust.sum()) if by_cust.sum() and st.session_state['wi_topn'] else 0.0

        params = dict(demand_pct=st.session_state['wi_demand'], price_pct=st.session_state['wi_price'],
                      discount_pp=st.session_state['wi_disc'], base_discount=base_disc, elasticity=st.session_state['wi_elast'],
                      lost_share=lost_share, lost_pct=st.session_state['wi_lostpct'], new_pct=st.session_state['wi_new'],
                      categories=cats_sel)
        res = run_scenario(cat, params)
        mo = res['monthly']
        base_total, scen_total = mo['baseline'].sum(), mo['scenario'].sum()
        fy24 = r24['sales'].sum()

        st.markdown("<br>", unsafe_allow_html=True)
        k = st.columns(4)
        with k[0]:
            kpi_card("Baseline revenue", fmt_money(base_total), base_name.split(' (')[0], "neutral")
        with k[1]:
            ch = pct_change(scen_total, base_total)
            text, tone = delta_badge(ch, "", note="vs baseline")
            kpi_card("Scenario revenue", fmt_money(scen_total), text, tone)
        with k[2]:
            kpi_card("Change in revenue", fmt_money(scen_total - base_total), "scenario − baseline", "positive" if scen_total >= base_total else "negative")
        with k[3]:
            uch = pct_change(mo['qty_scenario'].sum(), mo['qty_baseline'].sum())
            text, tone = delta_badge(uch, "", note="units vs baseline")
            kpi_card("Scenario units", fmt_num(mo['qty_scenario'].sum()), text, tone)
        st.caption(f"Net price vs today: {(res['price_mult'] - 1) * 100:+.1f}% · volume response: {(res['vol_mult'] - 1) * 100:+.1f}% · "
                   f"average discount becomes {res['net_discount'] * 100:.1f}% · top customers lost = {lost_share * 100:.1f}% of revenue · "
                   f"scenario vs FY2024 actual: {pct_change(scen_total, fy24) * 100:+.1f}%")

        left, right = st.columns(2)
        with left:
            st.markdown("### Baseline vs scenario by month")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=mo['month'], y=mo['baseline'], name="Baseline", line=dict(color='#333333', width=2.5)))
            fig.add_trace(go.Scatter(x=mo['month'], y=mo['scenario'], name="Scenario", line=dict(color='#E60012', width=3),
                                     fill='tonexty', fillcolor='rgba(230,0,18,0.10)'))
            show_chart(fig, height=360, x_title="Month", y_title=f"Revenue ({config.CURRENCY})", money='y')
        with right:
            st.markdown("### What moves the number")
            labels = [s[0] for s in res['steps']] + ['Scenario revenue']
            vals = [s[1] for s in res['steps']] + [0]
            fig = go.Figure(go.Waterfall(x=labels, y=vals, measure=['absolute', 'relative', 'relative', 'relative', 'relative', 'total'],
                                         increasing=dict(marker=dict(color='#005BAC')), decreasing=dict(marker=dict(color='#E60012')),
                                         totals=dict(marker=dict(color='#6C757D')), connector=dict(line=dict(color='#DDE1E6'))))
            show_chart(fig, height=360, legend=False, x_title="Step", y_title=f"Change in revenue ({config.CURRENCY})", money='y')

        st.markdown("### By category")
        bc = res['by_category']
        tbl = pd.DataFrame({"Category": bc['category'], "Baseline": bc['baseline'].round(0), "Scenario": bc['scenario'].round(0),
                            "Change %": (bc['change_pct'] * 100).round(1)})
        show_table(tbl, height=320)
        out = mo.assign(month=mo['month'].dt.strftime('%Y-%m')).round(0)
        csv_button(out, "Download scenario by month (CSV)", "what_if_scenario.csv")

        # ---- compare saved scenarios ----
        st.markdown("### Compare scenarios")
        saved = st.session_state.setdefault('wi_saved', [])
        s1, s2, s3 = st.columns([3, 1, 1])
        name = s1.text_input("Name this scenario", value="", key="wi_name", placeholder="e.g. Price +5%, lose top 3")
        s2.markdown("<br>", unsafe_allow_html=True)
        if s2.button("Save scenario", key="wi_save"):
            saved.append(dict(name=name.strip() or f"Scenario {len(saved) + 1}", total=float(scen_total), base=float(base_total)))
        s3.markdown("<br>", unsafe_allow_html=True)
        if s3.button("Clear saved", key="wi_clear"):
            saved.clear()
        if saved:
            fig = go.Figure(go.Bar(x=["Baseline"] + [s['name'] for s in saved], y=[base_total] + [s['total'] for s in saved],
                                   marker_color=['#6C757D'] + ['#E60012'] * len(saved)))
            show_chart(fig, height=320, legend=False, x_title="Scenario", y_title=f"Revenue ({config.CURRENCY})", money='y')
        note("<b>Assumptions, not predictions.</b> Levers are applied in this order: demand, price and discount "
             "(units respond through the elasticity), lost customers, new items. There are no cost figures in the data, "
             "so this shows revenue and units, not profit.")

    # =============================================================== inventory
    with tab_i:
        act = inv[inv['revenue_12m'] > 0]
        st.markdown("Compare today's stocking policy with a stressed one (demand surge, longer supplier delays, higher service level).")
        a1, a2 = st.columns(2)
        with a1:
            st.markdown("**Today's policy**")
            lead0 = st.slider("Lead time (months)", 0.5, 6.0, 2.0, 0.5, key="wi_lead0")
            sl0 = st.selectbox("Service level", [0.90, 0.95, 0.975, 0.99], index=1, format_func=lambda x: f"{x:.1%}", key="wi_sl0")
        with a2:
            st.markdown("**Scenario**")
            dm = st.slider("Demand change (%)", -40, 60, 0, key="wi_i_demand")
            delay = st.slider("Extra supplier delay (months)", 0.0, 4.0, 0.0, 0.5, key="wi_delay")
            sg = st.slider("Demand variability change (%)", -30, 100, 0, key="wi_sigma")
            sl1 = st.selectbox("Scenario service level", [0.90, 0.95, 0.975, 0.99], index=1, format_func=lambda x: f"{x:.1%}", key="wi_sl1")
        b = plan_reorder(act, lead0, sl0, 3)
        s = plan_reorder(act, lead0 + delay, sl1, 3, demand_mult=1 + dm / 100, sigma_mult=1 + sg / 100)
        price = act['avg_unit_price'].fillna(0)
        b_val, s_val = (b['safety'] * price).sum(), (s['safety'] * price).sum()
        k = st.columns(4)
        with k[0]:
            kpi_card("Safety stock (units)", fmt_num(s['safety'].sum()), f"today {fmt_num(b['safety'].sum())}", "neutral")
        with k[1]:
            text, tone = delta_badge(pct_change(s_val, b_val), "", note="value vs today", inverse=True)
            kpi_card("Safety stock value", fmt_money(s_val), text, tone)
        with k[2]:
            kpi_card("Reorder points (units)", fmt_num(s['rop'].sum()), f"today {fmt_num(b['rop'].sum())}", "neutral")
        with k[3]:
            up = int((s['rop'] > b['rop'] * 1.2).sum())
            kpi_card("Items needing a 20%+ higher reorder point", f"{up:,}", f"of {len(act):,} active items", "negative" if up else "positive")
        left, right = st.columns(2)
        with left:
            st.markdown("### Safety-stock value by ABC class")
            g = pd.DataFrame({'abc': act['abc'], 'Today': b['safety'] * price, 'Scenario': s['safety'] * price}).groupby('abc').sum().reindex(['A', 'B', 'C']).fillna(0)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=g.index, y=g['Today'], name="Today", marker_color='#6C757D'))
            fig.add_trace(go.Bar(x=g.index, y=g['Scenario'], name="Scenario", marker_color='#E60012'))
            fig.update_layout(barmode='group')
            show_chart(fig, height=340, x_title="ABC class", y_title=f"Safety-stock value ({config.CURRENCY})", money='y')
        with right:
            st.markdown("### Items with the biggest increase")
            d = pd.DataFrame({'Item': act['item'], 'Category': act['category'], 'ABC': act['abc'],
                              'Reorder point today': b['rop'], 'Reorder point scenario': s['rop'],
                              'Extra safety value': ((s['safety'] - b['safety']) * price).round(0)}).sort_values('Extra safety value', ascending=False)
            show_table(d.head(15), height=340)
        csv_button(d, "Download scenario reorder plan (CSV)", "what_if_reorder_plan.csv")
        note("Safety stock = z × demand variability × √lead time. A longer lead time or a higher service level raises it; "
             "the demand change also moves the reorder point. Unit prices are recent averages.")
