"""Add New Data: upload more orders, check them, include them in the dashboard and retrain the forecast."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from core import added_data as ad
from core.data import realised
from forecasting.live import train_updated, MIN_MONTHS
from ui.components import (back_bar, kpi_card, show_chart, show_table, csv_button, note,
                           fmt_money, fmt_num, pct_change, delta_badge)
from ui.model_panels import model_strip


def _set_use_added():
    st.session_state['use_added'] = st.session_state.get('hub_use_added', True)


def _remove_file(name):
    ad.remove(name)


def _show_report(rep, clean_df, ctx):
    k = st.columns(4)
    with k[0]:
        kpi_card("Rows read", f"{rep['rows_read']:,}", "in your file", "neutral")
    with k[1]:
        kpi_card("Rows accepted", f"{rep.get('rows_kept', 0):,}", "ready to add", "positive" if rep['ok'] else "negative")
    if rep['ok']:
        with k[2]:
            kpi_card("Date range", f"{rep['first']:%b %Y} to {rep['last']:%b %Y}", f"{rep['months']} month(s)", "neutral")
        with k[3]:
            kpi_card("Order value", fmt_money(rep['revenue']), "base price × quantity", "neutral")
    for p in rep['problems']:
        note(p, warn=True)
    if rep['dropped']:
        show_table(pd.DataFrame({"Rows removed": list(rep['dropped']), "Count": list(rep['dropped'].values())}))
    for w in rep['warnings']:
        note(w)
    if rep['ok']:
        known = set(ctx.df_all['customer'].astype(int))
        new_cust = int((~pd.to_numeric(clean_df['Customer Internal ID'], errors='coerce').fillna(0).astype(int).isin(known)).sum())
        if any('item master' in k for k in rep['dropped']):
            note("Rows for items that are not in the item master are removed, exactly as in the cleaning stage. "
                 "To include new items, import an updated Item file on the Import Data page first.")
        if new_cust:
            note(f"{new_cust:,} rows belong to customers not seen in the current data.")
        months_new = set(pd.to_datetime(clean_df['Sales Order Date']).dt.to_period('M'))
        months_old = set(ctx.df_all['date'].dt.to_period('M'))
        if months_new & months_old:
            note("Some months in this file already have data in the dashboard. Rows that match an existing order, item and date are skipped.")
        st.markdown("**Preview (first 15 rows)**")
        show_table(clean_df.head(15))


def render(ctx):
    back_bar('upload')
    st.markdown("## Add New Data")
    st.markdown("Add orders for future analysis. Files are checked first, saved in the `data/added/` folder, and then "
                "included in every page. You can then retrain the forecast on everything.")
    model_strip('upload', ctx)
    if st.session_state.get('hub_msg'):
        st.success(st.session_state.pop('hub_msg'))

    tab1, tab2, tab3 = st.tabs(["1 · Upload", "2 · Added files", "3 · Update forecast"])

    # ------------------------------------------------------------------ upload
    with tab1:
        left, right = st.columns([3, 2])
        with left:
            st.markdown("**What the file needs** (CSV or Excel, one row per order line)")
            show_table(pd.DataFrame({
                "Column": ["Sales Order Date", "Item Code", "Quantity", "Base Price", "Sales Order Number", "Customer Internal ID", "Sales Order Status"],
                "Required": ["yes", "yes", "yes", "yes", "no", "no", "no"],
                "Notes": ["date or Excel date number", "same codes as the item master", "above 0", "price per unit",
                          "generated if missing", "0 = unspecified", "Closed / Billed / other; Billed if missing"]}))
        with right:
            st.markdown("**Start from the template**")
            csv_button(ad.template(), "Download template (CSV)", "new_orders_template.csv", raw=True)
            st.caption("Excel files exported like TNIC_Data_2025.xlsx work as they are: the order sheet is found automatically.")
        up = st.file_uploader("Choose a file", type=["csv", "xlsx", "xlsm"], key="hub_file")
        if up is not None:
            sig = (up.name, up.size)
            if st.session_state.get('hub_sig') != sig:
                try:
                    raw = ad.read_any(up, up.name)
                    clean_df, rep = ad.clean(raw, existing=ctx.df_all, items=ctx.items_master)
                except Exception as e:                       # noqa: BLE001
                    clean_df, rep = None, dict(rows_read=0, problems=[f"Could not read the file: {e}"], dropped={}, warnings=[], ok=False)
                st.session_state.update(hub_sig=sig, hub_clean=clean_df, hub_rep=rep)
            clean_df, rep = st.session_state['hub_clean'], st.session_state['hub_rep']
            _show_report(rep, clean_df, ctx)
            if rep['ok']:
                if st.button("Add to dashboard data", key="hub_add", type="primary"):
                    ad.save(clean_df, up.name)
                    st.session_state['use_added'] = True
                    st.session_state['hub_msg'] = f"Added {len(clean_df):,} rows from {up.name}. All pages now include them."
                    st.session_state.pop('hub_sig', None)
                    st.rerun()

    # ------------------------------------------------------------------ added files
    with tab2:
        files = ad.list_added()
        st.toggle("Include added data in the dashboard", value=st.session_state.get('use_added', True),
                  key="hub_use_added", on_change=_set_use_added)
        if files.empty:
            st.info("Nothing added yet. Upload a file in step 1.")
        else:
            c = st.columns(3)
            with c[0]:
                kpi_card("Files", f"{len(files)}", "added so far", "neutral")
            with c[1]:
                kpi_card("Order lines", f"{int(files['rows'].sum()):,}", "added", "neutral")
            with c[2]:
                kpi_card("Date range", f"{files['first'].min():%b %Y} to {files['last'].max():%b %Y}", "", "neutral")
            show_table(files.rename(columns={'file': 'File', 'rows': 'Rows', 'first': 'First date', 'last': 'Last date', 'revenue': 'Order value'}).assign(**{'Order value': files['revenue'].round(0)}))
            for _, row in files.iterrows():
                st.button(f"Remove {row['file']}", key=f"hub_rm_{row['file']}", on_click=_remove_file, args=(row['file'],))
        note("The original FY2021-FY2024 history and the saved forecast results stay untouched. Added data feeds the "
             "Overview, Customers, Industries, Orders and Products pages; the validated FY2025 forecast and its accuracy "
             "keep their original training window.")

    # ------------------------------------------------------------------ update forecast
    with tab3:
        files = ad.list_added()
        o = ctx.outputs
        if files.empty:
            st.info("Add data first. Then you can retrain the forecast on history plus your new data.")
        elif not st.session_state.get('use_added', True):
            st.info("Turn on 'Include added data in the dashboard' in step 2 first.")
        else:
            last = ctx.df_all['date'].max()
            n_months = ctx.df_all['month'].nunique()
            st.markdown(f"Data available: **{ctx.df_all['date'].min():%b %Y} to {last:%b %Y}** ({n_months} months). "
                        f"The forecast covers the 12 months after the last complete month.")
            if st.button("Retrain forecast on all data", key="hub_train", type="primary"):
                try:
                    with st.spinner("Training (about 10-20 seconds)..."):
                        res = train_updated(ctx.df_all)
                    st.session_state['hub_msg'] = (f"Forecast updated: trained through {res['info']['trained_through']}, "
                                                   f"forecasting {res['info']['forecast_from']} to {res['info']['forecast_to']}.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        u = o.get('updated') if o else None
        if u:
            info, co, cat, inv = u['info'], u['company'], u['category'], u['inventory']
            st.markdown("---")
            st.markdown(f"### Updated forecast · {info.get('forecast_from', '')} to {info.get('forecast_to', '')}")
            st.caption(f"Trained through {info.get('trained_through', '')} on {info.get('order_lines', 0):,} order lines · updated {info.get('updated', '')}")
            for n in info.get('notes', []):
                note(n)
            r = realised(ctx.df_all)
            last12 = r[r['month'] > r['month'].max() - pd.DateOffset(months=12)]['sales'].sum()
            k = st.columns(4)
            with k[0]:
                kpi_card("Forecast, next 12 months", fmt_money(co['forecast'].sum()), "company revenue", "neutral")
            with k[1]:
                kpi_card("Last 12 months in data", fmt_money(last12), "realised revenue", "neutral")
            g = pct_change(co['forecast'].sum(), last12)
            with k[2]:
                text, tone = delta_badge(g, "", note="vs last 12 months")
                kpi_card("Expected growth", f"{g * 100:+.1f}%", text, tone)
            with k[3]:
                kpi_card("Items to review", f"{int((inv['flag'] == 'No sales 12+ months').sum()):,}", "no sales in 12+ months", "negative")
            hist = r.groupby('month')['sales'].sum()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hist.index, y=hist.values, name="Actual", line=dict(color='#333333', width=2)))
            fig.add_trace(go.Scatter(x=co['month'], y=co['hi'], line=dict(width=0), showlegend=False, hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=co['month'], y=co['lo'], line=dict(width=0), fill='tonexty',
                                     fillcolor='rgba(230,0,18,0.15)', name="~80% range", hoverinfo='skip'))
            fig.add_trace(go.Scatter(x=co['month'], y=co['forecast'], name="Updated forecast", mode='lines+markers',
                                     line=dict(color='#E60012', width=3)))
            show_chart(fig, height=380, x_title="Month", y_title=f"Revenue ({config.CURRENCY})", money='y')
            cc = cat.groupby('category')[['forecast', 'forecast_qty']].sum().sort_values('forecast', ascending=False).reset_index()
            show_table(pd.DataFrame({"Category": cc['category'], "Forecast revenue": cc['forecast'].round(0), "Forecast units": cc['forecast_qty'].round(0)}), height=300)
            d1, d2, d3 = st.columns(3)
            with d1:
                csv_button(co.assign(month=co['month'].dt.strftime('%Y-%m')), "Download company forecast (CSV)", "updated_forecast_company.csv")
            with d2:
                csv_button(cc, "Download category forecast (CSV)", "updated_forecast_category.csv")
            with d3:
                csv_button(inv, "Download inventory profile (CSV)", "updated_inventory_profile.csv")
            note("This forecast has no real results to compare with yet, so its accuracy is unknown. Expect roughly the "
                 "validation accuracy shown on the Model Accuracy page. The What-If page can use it as its baseline.")
