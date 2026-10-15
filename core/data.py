"""Data layer (no Streamlit imports so training scripts can reuse it).

history  : final_dataset_main.csv  (FY2021-FY2024, cleaned/encoded)  -> the dashboard's data. Either downloaded, or
                                    produced by the import pipeline (pipeline/) from the raw Customer / Item / Sale Order files.
actuals  : TNIC_Data_2025.xlsx     (FY2025 orders = real results used ONLY to score the forecast; cleaned with the SAME rules
                                    as the history. Its Item + Company sheets are the master tables unless the import
                                    pipeline has written data/processed/item_master.csv and customer_master.csv)
Both are mapped to ONE schema so every view and model sees the same columns.
"""
from pathlib import Path
import numpy as np
import pandas as pd

import config

EXCEL_ORIGIN = "1899-12-30"
HIST_COLS = ['Sales Order Date', 'Sales Order Number', 'Customer Internal Id', 'Item Code', 'Quantity',
             'Base Price', 'Total Sales Amount', 'Total Gross Value',
             'Sales Order Status Group_Loss', 'Sales Order Status Group_On going',
             'Production Status_Discontinue', 'Production Status_To Be Advised']
CAT_COLUMNS = ['category', 'category2', 'production', 'industry', 'segment', 'status', 'source', 'item', 'order']


def _clean_cols(df):
    df.columns = [str(c).strip() for c in df.columns]
    return df


STATUS_LABEL = {'Earned': 'Completed', 'On going': 'On going', 'Loss': 'Loss', 'Other': 'On going'}


def data_status(data_dir=None):
    """What is in the data folder? history = processed dataset CSV, master = item/customer tables, actuals = FY2025 workbook."""
    folder = Path(data_dir) if data_dir else config.DATA_DIR
    proc = folder / 'processed'
    history = config.find_data_file('history', folder)
    actuals = config.find_data_file('actuals', folder)
    master = (proc / 'item_master.csv').exists() and (proc / 'customer_master.csv').exists()
    master_source = 'processed' if master else ('workbook' if actuals is not None else None)
    return dict(history=history, actuals=actuals, master_source=master_source,
                ready=history is not None and master_source is not None)


def raw_master_tables(data_dir=None):
    """Raw Item and Customer tables with standard column names: from the import pipeline's output if present,
    otherwise from the Item / Company sheets of the FY2025 workbook."""
    from pipeline.readers import canonicalise, load_tables
    folder = Path(data_dir) if data_dir else config.DATA_DIR
    proc = folder / 'processed'
    if (proc / 'item_master.csv').exists() and (proc / 'customer_master.csv').exists():
        return (pd.read_csv(proc / 'item_master.csv', dtype={'Item Code': str}),
                pd.read_csv(proc / 'customer_master.csv'))
    xlsx = config.find_data_file('actuals', folder)
    if xlsx is None:
        raise FileNotFoundError("No item/customer master tables: import the raw files on the Import Data page, "
                                f"or put {config.ACTUALS_XLSX} in {folder}.")
    tables, _, problems = load_tables([(xlsx.name, xlsx)], roles=('items', 'customers'))
    if problems:
        raise ValueError("; ".join(problems))
    return canonicalise(tables['items'], 'items')[0], canonicalise(tables['customers'], 'customers')[0]


def load_master(data_dir=None):
    """Item and customer master tables indexed for look-ups (they cover every item/customer)."""
    items, cust = raw_master_tables(data_dir)
    items = items.copy()
    items['Item Code'] = items['Item Code'].astype(str)
    items = items.drop_duplicates("Item Code").set_index("Item Code")
    cust = cust.drop_duplicates("Customer Internal ID").set_index("Customer Internal ID")
    return items, cust


def _fiscal_year(dates):
    return np.where(dates.dt.month >= 4, dates.dt.year, dates.dt.year - 1)


def _finish(d, items, cust):
    """Add master attributes and calendar fields shared by both periods."""
    d['category'] = d['item'].map(items['Product Category 1']).fillna('Unknown')
    d['category2'] = d['item'].map(items['Product Category 2']).fillna('Unknown')
    d['production'] = d['item'].map(items['Production Status']).fillna('Continue')
    d['industry'] = d['customer'].map(cust['FA Sub Industries']).fillna('Unspecified')
    d['segment'] = np.where(d['customer'].map(cust['Customer Type']) == 'VIP', 'VIP', 'Non-VIP')
    d['discount'] = d['gross'] - d['sales']
    d['month'] = d['date'].dt.to_period('M').dt.to_timestamp()
    d['weekday'] = d['date'].dt.dayofweek
    d['fy'] = _fiscal_year(d['date']).astype(int)
    return d


REQUIRED_HIST = ['Sales Order Date', 'Sales Order Number', 'Customer Internal Id', 'Item Code', 'Quantity', 'Base Price',
                 'Total Sales Amount', 'Total Gross Value']
OPTIONAL_HIST = ['Sales Order Status Group_Loss', 'Sales Order Status Group_On going', 'Sales Order Status Group_Other',
                 'Production Status_Discontinue', 'Production Status_To Be Advised']


def load_history(csv_path, items, cust):
    header = list(pd.read_csv(csv_path, nrows=0).columns)
    missing = [c for c in REQUIRED_HIST if c not in header]
    if missing:
        raise ValueError(f"{Path(csv_path).name} is not a processed dataset (missing columns: {', '.join(missing)}). "
                         "Use the Import Data page to process the raw files.")
    raw = pd.read_csv(csv_path, usecols=[c for c in REQUIRED_HIST + OPTIONAL_HIST if c in header])
    flag = lambda name: raw[name] if name in raw else pd.Series(0, index=raw.index)    # noqa: E731
    d = pd.DataFrame({
        'date': pd.to_datetime(raw['Sales Order Date']),
        'order': raw['Sales Order Number'].astype(str),
        'customer': raw['Customer Internal Id'].astype('int64'),
        'item': raw['Item Code'].astype(str),
        'qty': raw['Quantity'].astype('float64'),
        'price': raw['Base Price'].astype('float64'),
        'sales': raw['Total Sales Amount'].astype('float64'),
        'gross': raw['Total Gross Value'].astype('float64'),
    })
    d['status'] = np.where(flag('Sales Order Status Group_Loss') > 0, 'Loss',
                           np.where((flag('Sales Order Status Group_On going') > 0) | (flag('Sales Order Status Group_Other') > 0),
                                    'On going', 'Completed'))
    # production flag as recorded in the history file (avoids look-ahead in backtests)
    d['production_hist'] = np.where(flag('Production Status_Discontinue') > 0, 'Discontinue',
                                    np.where(flag('Production Status_To Be Advised') > 0, 'To Be Advised', 'Continue'))
    d['source'] = 'history'
    return _finish(d, items, cust)


def _parse_dates(s):
    """Excel serial numbers or ordinary date strings."""
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_datetime(s, unit='D', origin=EXCEL_ORIGIN)
    return pd.to_datetime(s, errors='coerce')


def _orders_to_frame(raw, items, cust, source):
    """raw columns: Sales Order Date, Sales Order Number, Customer Internal ID, Item Code, Quantity, Base Price,
    Sales Order Status.  Anything not in the item/customer master gets 'Unknown' / 'Unspecified'."""
    code = raw['Item Code'].astype(str)
    d = pd.DataFrame({
        'date': _parse_dates(raw['Sales Order Date']),
        'order': raw['Sales Order Number'].astype(str),
        'customer': pd.to_numeric(raw['Customer Internal ID'], errors='coerce').fillna(0).astype('int64'),
        'item': code,
        'qty': raw['Quantity'].astype('float64'),
        'price': raw['Base Price'].astype('float64'),
    })
    d['sales'] = d['price'] * d['qty']
    # list price is only available as the current master value
    d['gross'] = np.maximum(code.map(items['List price']).astype(float).fillna(0) * d['qty'], d['sales'])
    from pipeline.transform import status_group
    d['status'] = pd.Series(status_group(raw['Sales Order Status'].astype(str).str.strip())).map(STATUS_LABEL).to_numpy()
    d['production_hist'] = None
    d['source'] = source
    return _finish(d, items, cust)


def load_actuals(data_dir, items, cust):
    """FY2025 orders from the workbook, cleaned with the same rules as the history (pipeline Stage 1 + quantity > 0)."""
    from pipeline.clean import clean
    from pipeline.readers import load_tables
    from pipeline.transform import status_group
    xlsx = config.find_data_file('actuals', data_dir)
    tables, _, problems = load_tables([(xlsx.name, xlsx)])
    if problems:
        raise ValueError("; ".join(problems))
    cleaned = clean(tables['customers'], tables['items'], tables['orders'])
    cleaned = cleaned[cleaned['Quantity'] > 0]
    d = pd.DataFrame({
        'date': pd.to_datetime(cleaned['Sales Order Date']).to_numpy(),
        'order': cleaned['Sales Order Number'].astype(str).to_numpy(),
        'customer': cleaned['Customer Internal Id'].astype('int64').to_numpy(),
        'item': cleaned['Item Code'].astype(str).to_numpy(),
        'qty': cleaned['Quantity'].astype('float64').to_numpy(),
        'price': cleaned['Base Price'].astype('float64').to_numpy(),
    })
    d['sales'] = d['price'] * d['qty']
    d['gross'] = (cleaned['List Price'].astype('float64') * cleaned['Quantity']).to_numpy()
    d['status'] = pd.Series(status_group(cleaned['Sales Order Status'])).map(STATUS_LABEL).to_numpy()
    d['production_hist'] = None
    d['source'] = 'actual_fy25'
    return _finish(d, items, cust)


def load_added(items, cust, added_dir=None):
    """Orders the user added through the 'Add New Data' page (standardised CSVs in data/added/)."""
    folder = Path(added_dir or config.DATA_DIR / 'added')
    files = sorted(folder.glob('*.csv')) if folder.exists() else []
    if not files:
        return None
    raw = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    return _orders_to_frame(raw, items, cust, 'added')


def build_dataset(data_dir=None, include_actuals=False, include_added=False):
    """Return (dataframe, items_master, customer_master).

    The dashboard uses include_actuals=False: only the FY2021-FY2024 history is "the data".
    The FY2025 orders in TNIC_Data_2025.xlsx are the real results to compare forecasts against, so only the
    training/evaluation scripts load them (include_actuals=True). The item/customer master tables are always read."""
    folder = Path(data_dir) if data_dir else config.DATA_DIR
    csv_path = config.find_data_file("history", folder)
    if csv_path is None:
        raise FileNotFoundError(f"Need {config.HISTORY_CSV} in {folder}. Download it (link in the README) or use Import Data.")
    items, cust = load_master(folder)
    parts = [load_history(csv_path, items, cust)]
    if include_actuals:
        parts.append(load_actuals(folder, items, cust))
    if include_added:
        added = load_added(items, cust)
        if added is not None:
            parts.append(added)
    df = pd.concat(parts, ignore_index=True)
    df = df.sort_values('date', kind='stable').reset_index(drop=True)
    for c in CAT_COLUMNS:
        df[c] = df[c].astype('category')
    return df, items, cust


def realised(df):
    """Orders that represent real demand (Closed/'Loss' orders are excluded)."""
    return df[~df['status'].isin(config.FORECAST_EXCLUDE_STATUS)]
