"""Import & Process Data: drop the raw Customer, Item and Sale Order History files; the dashboard cleans, transforms
and encodes them (the three notebook stages) and writes the dataset it displays.
Also used as the first-run welcome screen when no dataset is in the data folder (ctx is None)."""
import json

import pandas as pd
import streamlit as st

import config
from core.data import data_status
from pipeline import run_pipeline, write_outputs, load_tables
from pipeline.schema import ROLE_NAMES
from ui.components import back_bar, kpi_card, show_table, csv_button, note, go as goto
from ui.model_panels import model_strip

ACCEPT = ["xlsx", "xlsm", "csv"]


def _read_files(files):
    """Detect which table each file / sheet is. Cached in the session so big Excel files are read only once."""
    sig = tuple((f.name, f.size) for f in files)
    if st.session_state.get('imp_sig') != sig:
        tables, found, problems = load_tables([(f.name, f) for f in files])
        st.session_state.update(imp_sig=sig, imp_tables=tables, imp_found=found, imp_problems=problems, imp_result=None)
    return st.session_state['imp_tables'], st.session_state['imp_found'], st.session_state['imp_problems']


def _last_report():
    p = config.PROCESSED_DIR / 'processing_report.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def _show_report(rep_steps, summary, seconds):
    k = st.columns(5)
    with k[0]:
        kpi_card("Rows read", f"{summary['rows_in']:,}", "Sale Order History", "neutral")
    with k[1]:
        kpi_card("Rows in the dataset", f"{summary['rows_out']:,}", f"{summary['rows_in'] - summary['rows_out']:,} removed", "positive")
    with k[2]:
        kpi_card("Columns", f"{summary['columns']}", "after encoding", "neutral")
    with k[3]:
        kpi_card("Period", f"{summary['first_date'][:7]} to {summary['last_date'][:7]}", f"{summary['items']:,} items · {summary['customers']:,} customers", "neutral")
    with k[4]:
        kpi_card("Processing time", f"{seconds}s", "all three stages", "neutral")
    steps = pd.DataFrame(rep_steps)
    for stage, g in steps.groupby('stage', sort=False):
        with st.expander(f"{stage} · {len(g)} steps", expanded=False):
            show_table(pd.DataFrame({"Step": g['step'], "What happened": g['title'] + ": " + g['detail'],
                                     "Rows after": g['rows'].map(lambda v: "" if pd.isna(v) else f"{int(v):,}")}))
    csv_button(steps.rename(columns={'stage': 'Stage', 'step': 'Step', 'title': 'Title', 'detail': 'Detail', 'rows': 'Rows', 'removed': 'Removed'}),
               "Download the processing report (CSV)", "processing_report.csv", raw=True)


def _rebuild_forecasts():
    """Re-run the forecast pipeline on the current dataset (about 2 minutes)."""
    from scripts import train_forecasts
    with st.spinner("Rebuilding the forecasts (about 2 minutes)..."):
        train_forecasts.main()


def render(ctx=None):
    setup = ctx is None
    status = data_status()
    if not setup:
        back_bar('import')
    st.markdown("## Import & Process Data" if not setup else "## Welcome: let's load the data")
    if setup:
        st.markdown("The dashboard needs its dataset before it can show anything. There are two ways to get it:")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Option 1 · Download the ready dataset**")
            st.markdown(f"Download `{config.HISTORY_CSV}` from Google Drive, put it in the `data` folder, then reload this page.")
            if config.DATA_DOWNLOAD_URL:
                st.link_button("Open Google Drive", config.DATA_DOWNLOAD_URL)
            st.caption(f"Data folder: ./mitsubishi_dashboard/data")
        with c2:
            st.markdown("**Option 2 · Import the raw files (below)**")
            st.markdown("Drop the raw **Customer**, **Item** and **Sale Order History** files. The dashboard cleans and prepares "
                        "everything for you. Needs no other file.")
        if status['history'] is not None and status['master_source'] is None:
            note("The dataset is there, but the Item and Customer master tables are missing. Import the raw Customer and Item files "
                 f"below, or put {config.ACTUALS_XLSX} in the data folder.", warn=True)
        st.markdown("---")
    else:
        st.markdown("Drop your raw files and the dashboard does the rest: cleaning, feature engineering and encoding, "
                    "then it shows the result on every page.")
    model_strip('import', ctx)

    rep = _last_report()
    if status['ready'] and not setup:
        cur = f"`{status['history'].name}`" + (f" · last processed {rep['processed_at']}" if rep else " · supplied as a ready file")
        note(f"Current dataset: {cur}. Importing new files replaces it.")

    # ---------------------------------------------------------------- step 1: upload
    st.markdown("### 1 · Add the raw files")
    st.caption("Excel or CSV. You can drop the three files together, or one workbook that holds all three sheets "
               "(like TNIC_Data_2025.xlsx). The dashboard works out which table is which.")
    files = st.file_uploader("Raw files", type=ACCEPT, accept_multiple_files=True, key="imp_files")
    if not files:
        if not setup:
            st.info("Waiting for files.")
        return
    with st.spinner("Reading the files..."):
        tables, found, problems = _read_files(files)
    show_table(pd.DataFrame({"Table": [ROLE_NAMES[r] for r, _, _ in found], "Found in": [s for _, s, _ in found],
                             "Rows": [f"{n:,}" for _, _, n in found]}) if found else pd.DataFrame({"Table": [], "Found in": [], "Rows": []}))
    for p in problems:
        note(p, warn=True)
    complete = {'orders', 'customers', 'items'} <= set(tables)

    # ---------------------------------------------------------------- step 2: process
    st.markdown("### 2 · Process")
    replace_ok = True
    if status['ready'] and not setup:
        replace_ok = st.checkbox("Replace the current dataset with the processed result", value=False, key="imp_replace")
    if st.button("Clean, transform and encode the data", key="imp_run", type="primary", disabled=not (complete and replace_ok)):
        bar = st.progress(0.0, text="Starting...")
        try:
            result = run_pipeline(tables['customers'], tables['items'], tables['orders'],
                                  progress=lambda f, t: bar.progress(min(f, 0.99), text=t))
            bar.progress(0.99, text="Saving the dataset...")
            write_outputs(result, config.DATA_DIR)
            bar.progress(1.0, text="Done")
            st.session_state['imp_result'] = dict(steps=result.log.steps, summary=result.summary, seconds=result.seconds)
            st.session_state['imp_msg'] = f"Processed {result.summary['rows_in']:,} rows into {result.summary['rows_out']:,} clean rows. The dashboard now uses them."
            if setup:
                st.rerun()
        except Exception as e:                                                   # noqa: BLE001
            bar.empty()
            st.error(f"Processing stopped: {e}")
    if not complete:
        st.caption("The button unlocks when all three tables are found.")

    res = st.session_state.get('imp_result')
    if res:
        st.success(st.session_state.pop('imp_msg', "Processed."))
        _show_report(res['steps'], res['summary'], res['seconds'])
        st.markdown("### 3 · Use it")
        a, b = st.columns(2)
        with a:
            st.button("Open the dashboard →", key="imp_open", on_click=goto, args=('home',))
        with b:
            if st.button("Rebuild the forecasts for this data (optional, about 2 minutes)", key="imp_rebuild"):
                try:
                    _rebuild_forecasts()
                    st.success("Forecasts rebuilt.")
                except Exception as e:                                               # noqa: BLE001
                    st.error(f"Could not rebuild the forecasts: {e}")
        note("The saved forecasts and accuracy tables were built from the original dataset. If you imported different data, "
             "rebuild the forecasts here. The accuracy tables update when you run <code>python -m scripts.evaluate_models</code>.")
