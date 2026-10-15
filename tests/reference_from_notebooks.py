"""Runs the data-processing cells of YOUR notebooks (notebooks/*.ipynb) in memory and returns their results.
It is the reference the ported pipeline (pipeline/) is tested against: same input, same output.
Display / print-only cells and the Excel save/load round trips are skipped."""
import contextlib
import io
import json
import pathlib

import numpy as np
import pandas as pd

NB = pathlib.Path(__file__).resolve().parents[1] / 'notebooks'


def _cells(name):
    d = json.load(open(NB / name, encoding='utf-8'))
    return {i: ''.join(c['source']) for i, c in enumerate(d['cells']) if c['cell_type'] == 'code'}


def run_notebooks(customer, item, orders):
    """customer / item / orders: raw DataFrames (dates already real datetimes). Returns dict of the notebook results."""
    ns = {'np': np, 'pd': pd}
    quiet = io.StringIO()
    with contextlib.redirect_stdout(quiet):
        # ---------------- clean_data.ipynb ----------------
        c = _cells('clean_data.ipynb')
        exec(c[1], ns)                                              # imports
        ns['data'] = [customer.copy(), item.copy(), orders.copy()]
        ns['files'] = ['Customer', 'Item', 'Sale Order History']
        for df in ns['data']:                                       # cell 4: strip column names (load replaced by inputs)
            df.columns = df.columns.str.strip()
        exec(c[10], ns)                                             # drop duplicates (Sale Order History only)
        exec(c[16], ns)                                             # merge customer + item, remove zero-price rows
        ns['final_df'] = ns['final_df'].copy()
        exec(c[23], ns)                                             # Title-Case the column names
        cleaned = ns['final_df'].copy()
        # ---------------- data_transformation.ipynb ----------------
        t = _cells('data_transformation.ipynb')
        ns['df'] = ns['final_df']                                   # cell 3 loads Cleaned_Sales.xlsx; here: in memory
        for i in (6, 9, 11, 13, 15, 17, 19, 21, 23, 27, 29, 31, 33, 35, 37, 39, 42, 44, 46, 49, 51, 54, 57, 60, 62, 65, 67,
                  71, 75, 77, 81):
            exec(t[i], ns)
        transformed = ns['df'].copy()
        inventory = ns['inventory_features'].copy()
        # ---------------- data_encode.ipynb ----------------
        e = _cells('data_encode.ipynb')
        ns['df_sales'], ns['df_inv'] = ns['df'], ns['inventory_features']
        for i in (7, 11, 13, 15):
            exec(e[i], ns)
        code18 = '\n'.join(l for l in e[18].splitlines() if 'to_excel' not in l and 'to_csv' not in l)
        exec(code18, ns)
    return dict(cleaned=cleaned, transformed=transformed, inventory=inventory, final=ns['df_final'].copy())
