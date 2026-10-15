"""'Add New Data': read, validate and store extra order files (no Streamlit imports).

Accepted: CSV or Excel with one row per order line. Columns can be named like in TNIC_Data_2025.xlsx
('FY25 - Sale Order History' sheet) or with common aliases. Cleaned rows are saved as standardised CSVs in
data/added/, which the dashboard then merges into its data."""
from datetime import datetime
from pathlib import Path
import re
import numpy as np
import pandas as pd

import config
from core.data import _parse_dates

ADDED_DIR = config.DATA_DIR / 'added'
STANDARD = ['Sales Order Date', 'Sales Order Number', 'Customer Internal ID', 'Item Code', 'Quantity', 'Base Price',
            'Sales Order Status']
REQUIRED = ['Sales Order Date', 'Item Code', 'Quantity', 'Base Price']          # the rest have safe defaults
ALIASES = {
    'Sales Order Date': ['salesorderdate', 'orderdate', 'date'],
    'Sales Order Number': ['salesordernumber', 'ordernumber', 'orderno', 'order'],
    'Customer Internal ID': ['customerinternalid', 'customerid', 'customer'],
    'Item Code': ['itemcode', 'item', 'sku', 'partnumber'],
    'Quantity': ['quantity', 'qty'],
    'Base Price': ['baseprice', 'unitprice', 'price'],
    'Sales Order Status': ['salesorderstatus', 'orderstatus', 'status'],
}


def _key(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def template():
    return pd.DataFrame({
        'Sales Order Date': ['2026-04-02', '2026-04-03'], 'Sales Order Number': ['SO-0001', 'SO-0002'],
        'Customer Internal ID': [1001, 1002], 'Item Code': ['ABC', 'XYZ'], 'Quantity': [10, 4],
        'Base Price': [1250.0, 8900.0], 'Sales Order Status': ['Billed', 'Pending']})


def read_any(file, filename):
    """CSV or Excel -> raw DataFrame. For Excel the sheet with the order columns is chosen automatically."""
    if str(filename).lower().endswith(('.xlsx', '.xlsm', '.xls')):
        xl = pd.ExcelFile(file)
        best = None
        for sheet in xl.sheet_names:
            head = xl.parse(sheet, nrows=5)
            keys = {_key(c) for c in head.columns}
            hits = sum(any(a in keys for a in ALIASES[col]) for col in REQUIRED)
            if best is None or hits > best[0]:
                best = (hits, sheet)
        return xl.parse(best[1])
    return pd.read_csv(file)


def standardise(raw):
    """Rename columns to the standard names. Returns (frame, problems)."""
    keys = {_key(c): c for c in raw.columns}
    out, problems = pd.DataFrame(index=raw.index), []
    for col in STANDARD:
        src = next((keys[a] for a in ALIASES[col] if a in keys), None)
        if src is not None:
            out[col] = raw[src]
        elif col in REQUIRED:
            problems.append(f"Missing required column: {col}")
    return out, problems


def clean(raw, existing=None, items=None):
    """Validate and clean an upload with the SAME rules as the cleaning stage of the import pipeline.
    Returns (clean_df, report dict).  `existing` = current dashboard data (to spot rows already there);
    `items` = item master (list prices, to apply the unpriced-row rule)."""
    std, problems = standardise(raw)
    rep = dict(rows_read=len(raw), problems=problems, dropped={}, warnings=[], ok=False)
    if problems:
        return None, rep
    df = std.copy()
    df['Sales Order Date'] = _parse_dates(df['Sales Order Date'])
    df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
    df['Base Price'] = pd.to_numeric(df['Base Price'], errors='coerce')
    df['Item Code'] = df['Item Code'].astype(str).str.strip()
    if 'Sales Order Number' not in df:
        df['Sales Order Number'] = [f"ADD-{i + 1:06d}" for i in range(len(df))]
        rep['warnings'].append("No order number column: numbers were generated.")
    if 'Customer Internal ID' not in df:
        df['Customer Internal ID'] = 0
        rep['warnings'].append("No customer column: customers are shown as 'Unspecified'.")
    if 'Sales Order Status' not in df:
        df['Sales Order Status'] = 'Billed'
        rep['warnings'].append("No status column: every row was treated as Billed.")

    def drop(mask, why):
        n = int(mask.sum())
        if n:
            rep['dropped'][why] = n
        return df[~mask]

    df = drop(df['Sales Order Date'].isna(), "date missing or unreadable")
    df = drop(df['Item Code'].isin(['', 'nan', 'None']), "item code missing")
    df = drop(df['Quantity'].isna() | (df['Quantity'] <= 0), "quantity missing or not above 0")
    df = drop(df['Base Price'].isna() | (df['Base Price'] < 0), "price missing or negative")
    n = len(df)
    df = df.drop_duplicates()                                  # Step 1.3: exact duplicate rows
    if len(df) < n:
        rep['dropped']["exact duplicate rows (same rule as the cleaning stage)"] = n - len(df)
    if items is not None and len(df):                          # Step 1.4: rows without a usable list price
        lp = df['Item Code'].map(items['List price'])
        unpriced = lp.isna() | ((df['Base Price'] == 0) & (lp == 0))
        if unpriced.any():
            rep['dropped']["item not in the item master / list price missing, or price and list price both 0 (cleaning rule)"] = int(unpriced.sum())
            df = df[~unpriced]
    if existing is not None and len(df):
        key_new = df['Sales Order Number'].astype(str) + '|' + df['Item Code'] + '|' + df['Sales Order Date'].dt.strftime('%Y-%m-%d')
        key_old = set(existing['order'].astype(str) + '|' + existing['item'].astype(str) + '|' + existing['date'].dt.strftime('%Y-%m-%d'))
        dup = key_new.isin(key_old)
        if dup.any():
            rep['dropped']["already in the dashboard data"] = int(dup.sum())
            df = df[~dup]
    df['Sales Order Date'] = df['Sales Order Date'].dt.strftime('%Y-%m-%d')
    df = df[STANDARD].reset_index(drop=True)
    rep.update(rows_kept=len(df), ok=len(df) > 0)
    if len(df):
        d = pd.to_datetime(df['Sales Order Date'])
        rep.update(first=d.min(), last=d.max(), months=int(d.dt.to_period('M').nunique()),
                   revenue=float((df['Quantity'] * df['Base Price']).sum()))
    return df, rep


def unknown_counts(df, items, cust):
    ni = int((~df['Item Code'].isin(items.index.astype(str))).sum())
    nc = int((~pd.to_numeric(df['Customer Internal ID'], errors='coerce').isin(cust.index)).sum())
    return ni, nc


def save(df, original_name):
    ADDED_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[^A-Za-z0-9_-]+', '_', Path(original_name).stem)[:40] or 'upload'
    path = ADDED_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{stem}.csv"
    df.to_csv(path, index=False)
    return path


def list_added():
    rows = []
    for p in sorted(ADDED_DIR.glob('*.csv')) if ADDED_DIR.exists() else []:
        d = pd.read_csv(p, usecols=['Sales Order Date', 'Quantity', 'Base Price'])
        dates = pd.to_datetime(d['Sales Order Date'])
        rows.append(dict(file=p.name, rows=len(d), first=dates.min().date(), last=dates.max().date(),
                         revenue=float((d['Quantity'] * d['Base Price']).sum())))
    return pd.DataFrame(rows)


def remove(file_name):
    p = ADDED_DIR / Path(file_name).name
    if p.exists():
        p.unlink()
