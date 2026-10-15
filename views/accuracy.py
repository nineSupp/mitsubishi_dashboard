"""Q4: How accurate are the models?
Stage 1 validation (history only): FY2023 and FY2024.  Stage 2 final test: forecast FY2025, compare with the real results."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from core.analytics import category_accuracy, company_accuracy
from core.model_registry import used_for, TESTED_ONLY
from ui.components import back_bar, kpi_card, show_chart, show_table, csv_button, note, fmt_pct, fmt_money
from ui.model_panels import model_strip, model_map, tested_only_table, team_models_panel, _flat
from views._guard import require_outputs

STAGES = """
<div class="stage-strip">
<div class="stage"><div class="stage-h">Stage 1 · Validation</div><div class="stage-t">Train FY2021-22 → test FY2023</div>
<div class="stage-d">Train FY2021-23 → test FY2024. History only; this is where the models are ranked and chosen.</div></div>
<div class="stage final"><div class="stage-h">Stage 2 · Final test</div><div class="stage-t">Train FY2021-24 → forecast FY2025</div>
<div class="stage-d">Compared with the real FY2025 orders in TNIC_Data_2025.xlsx, which are never used for training.</div></div>
</div>
"""


def render(ctx):
    back_bar('accuracy')
    st.markdown("## Model Accuracy")
    st.markdown("Every model is tested the same way: train only on earlier months, forecast a full year, compare with what "
                "really happened. Accuracy = 1 − WAPE (higher is better).")
    model_strip('accuracy', ctx)
    if not require_outputs(ctx):
        return
    o = ctx.outputs
    acc = company_accuracy(o['company'])
    st.markdown(_flat(STAGES), unsafe_allow_html=True)

    cols = st.columns(4)
    with cols[0]:
        kpi_card("FY2025 Monthly Accuracy", fmt_pct(acc['monthly'], 1), "company revenue vs real results", "neutral")
    with cols[1]:
        kpi_card("FY2025 Full-Year Error", f"{acc['year_error'] * 100:+.1f}%", "forecast vs real total",
                 "negative" if abs(acc['year_error']) > 0.15 else "positive")
    with cols[2]:
        kpi_card("Forecast / Real", f"{fmt_money(acc['forecast'])} / {fmt_money(acc['actual'])}", "FY2025 revenue", "neutral")
    with cols[3]:
        kpi_card("Validation folds", "2", "FY2023 · FY2024", "neutral")
    st.markdown("<br>", unsafe_allow_html=True)

    ev = o['eval']
    level = st.radio("Compare models at level", ["Company x month", "Company x year", "Category x month", "SKU x month"],
                     horizontal=True, key="acc_level")
    t = ev[(ev['Target'] == 'Revenue') & (ev['Level'] == level)].pivot_table(index='Model', columns='Fold', values='Accuracy')
    for c in ('FY2023', 'FY2024', 'FY2025'):
        if c not in t.columns:
            t[c] = np.nan
    if level.startswith('Company'):      # top-down variants reuse the company total, so they repeat the GBM row
        t = t[~t.index.str.startswith('Top-down')]
    t['Validation mean'] = t[['FY2023', 'FY2024']].mean(axis=1)
    t = t.sort_values('Validation mean', ascending=False)
    t['Used for'] = [used_for(m) or 'Tested only' for m in t.index]
    is_used = t['Used for'] != 'Tested only'

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"### Revenue accuracy by model ({level})")
        fig = go.Figure()
        fig.add_trace(go.Bar(y=t.index, x=t['FY2024'] * 100, name="Validation FY2024", orientation='h',
                             marker_color=np.where(is_used, '#005BAC', '#DBDBDB')))
        fig.add_trace(go.Bar(y=t.index, x=t['FY2025'] * 100, name="Final test FY2025", orientation='h',
                             marker_color=np.where(is_used, '#E60012', '#8C8C8C')))
        fig.update_layout(barmode='group')
        fig.update_xaxes(title="Accuracy %  (coloured bars = model used in the dashboard, grey = tested only)", range=[0, 100])
        fig.update_yaxes(autorange='reversed')
        show_chart(fig, height=560, y_title="Model")
    with right:
        st.markdown("### Scores")
        tbl = t.copy()
        for c in ('FY2023', 'FY2024', 'FY2025', 'Validation mean'):
            tbl[c] = (tbl[c] * 100).round(1)
        tbl = tbl.rename(columns={'FY2023': 'Val. FY2023', 'FY2024': 'Val. FY2024', 'FY2025': 'Final FY2025'}).reset_index()
        show_table(tbl, height=560)
        csv_button(tbl, "Download scores (CSV)", "model_accuracy.csv")

    note("<b>Why FY2023 is not a fair ranking:</b> revenue fell about a third that year and every model over-forecast "
         "(nobody predicted the drop). It is a warning that forecasts cannot see sudden market shocks.", warn=True)

    st.markdown("### Your team's four quantity models")
    team_models_panel(ev)

    st.markdown("### FY2025 forecast vs real results by category")
    cat = category_accuracy(o['category'])
    cat = cat[cat['actual'] > 0].head(12)
    left, right = st.columns([2, 3])
    with left:
        show_table(pd.DataFrame({"Category": cat['category'], "Real": cat['actual'].round(0),
                                 "Forecast": cat['forecast'].round(0), "Full-year error %": (cat['bias'] * 100).round(1),
                                 "Monthly accuracy %": (cat['accuracy'] * 100).round(1)}), height=420)
    with right:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=cat['category'], y=cat['forecast'], name="Forecast", marker_color='#E60012'))
        fig.add_trace(go.Bar(x=cat['category'], y=cat['actual'], name="Real FY2025", marker_color='#005BAC'))
        fig.update_layout(barmode='group')
        show_chart(fig, height=420, x_title="Product category", y_title=f"Revenue ({config.CURRENCY})", money='y')

    st.markdown("### FY2025 company revenue: every candidate model vs the real result")
    bm = o['by_model']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bm['month'], y=bm['actual'], name="Real FY2025", line=dict(color='#333333', width=3.5)))
    palette = ['#E60012', '#005BAC', '#8C8C8C', '#F26B76', '#5B9BD5', '#B3001B']
    for i, c in enumerate([c for c in bm.columns if c not in ('month', 'actual')]):
        used = bool(used_for(c))
        fig.add_trace(go.Scatter(x=bm['month'], y=bm[c], name=c + (" (used)" if used else ""),
                                 line=dict(color=palette[i % len(palette)], width=3 if used else 1.5, dash='solid' if used else 'dot')))
    show_chart(fig, height=400, x_title="Month", y_title=f"Company revenue ({config.CURRENCY})", money='y')

    st.markdown("### Which model powers what")
    model_map(ev)
    with st.expander("Models tested but not used, and why"):
        show_table(tested_only_table())
    with st.expander("What the backtest shows (read this before choosing a model)"):
        st.markdown(
            "- **Company total:** Gradient Boosting was the most accurate in validation (FY2024) and held up in the final FY2025 test.\n"
            "- **Item-by-month forecasts are weak for every method** (roughly 15-35% accuracy) because most items sell "
            "rarely and in lumps. Use them for ranking and safety stock, not exact monthly numbers.\n"
            "- **Random-forest / hurdle designs** (from the shared project) were tested in the same leak-free way and "
            "scored below simple averages at company and category level.\n"
            "- Brand-new products have no list price yet, so the cleaning rules exclude them (about ฿108M of FY2025 orders). No history-based model can forecast them.")
