"""Stage 1: Data Cleaning  (notebooks/clean_data.ipynb, steps 1.1 - 1.7)."""
import numpy as np
import pandas as pd

from pipeline.log import StepLog
from pipeline.readers import canonicalise
from pipeline.schema import ROLE_NAMES

STAGE = 'Stage 1 · Cleaning'


def parse_dates(s):
    """Real dates, Excel serial numbers or date text."""
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_datetime(s, unit='D', origin='1899-12-30')
    return pd.to_datetime(s, errors='coerce')


def _ids_to_numbers(df, cols):
    for c in cols:
        if c in df and df[c].dtype == object:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def prepare(customers, items, orders, log):
    """Step 1.1 and 1.2: load the three tables, strip column names, list the attributes."""
    out, issues = {}, []
    for role, df in (('customers', customers), ('items', items), ('orders', orders)):
        frame, missing = canonicalise(df, role)
        if missing:
            issues.append(f"{ROLE_NAMES[role]} is missing: {', '.join(missing)}")
        out[role] = frame
    if issues:
        raise ValueError("; ".join(issues))
    orders = out['orders']
    if 'SO Internal ID' not in orders:                       # only used to count orders per item later
        orders.insert(0, 'SO Internal ID', np.arange(1, len(orders) + 1))
    orders['Sales Order Date'] = parse_dates(orders['Sales Order Date'])
    for role, cols in (('orders', ['Customer Internal ID', 'Item Internal ID']), ('customers', ['Customer Internal ID']),
                       ('items', ['Item Internal ID'])):
        _ids_to_numbers(out[role], cols)
    log.add(STAGE, '1.1', 'Load the 3 files', f"Customer {len(out['customers']):,} rows · Item {len(out['items']):,} rows · "
            f"Sale Order History {len(orders):,} rows. Whitespace stripped from every column name.", rows=len(orders))
    log.add(STAGE, '1.2', 'Attribute names', "Columns checked: " + " · ".join(f"{ROLE_NAMES[r]} {len(out[r].columns)}" for r in out))
    return out['customers'], out['items'], out['orders']


def clean(customers, items, orders, log=None):
    """Return the cleaned, merged sales table with Title-Case column names (Cleaned_Sales)."""
    log = log if log is not None else StepLog()
    customers, items, orders = prepare(customers, items, orders, log)

    # Step 1.3  duplicated rows: only Sale Order History has them, so only it is de-duplicated
    n0 = len(orders)
    orders = orders.drop_duplicates()
    log.add(STAGE, '1.3', 'Duplicated rows', f"{n0 - len(orders):,} exact duplicate rows removed from Sale Order History "
            f"({len(orders):,} left).", rows=len(orders), removed=n0 - len(orders))

    # Step 1.4  merge customer and item information, then drop zero-price / unlisted rows
    sales_with_cus = pd.merge(
        orders, customers[['Customer Internal ID', 'Company Name', 'Customer Type', 'FA Sub Industries']],
        on=['Customer Internal ID', 'Company Name'], how='left')
    final_df = pd.merge(
        sales_with_cus, items[['Item Internal ID', 'Item Code', 'Production Status', 'Product Category 1',
                               'Product Category 2', 'List price']],
        on=['Item Internal ID', 'Item Code'], how='left')
    n1 = len(final_df)
    zero_price_mask = ((final_df['Base Price'] == 0) & (final_df['List price'] == 0)) | (final_df['List price'].isna())
    final_df = final_df[~zero_price_mask]
    log.add(STAGE, '1.4', 'Merge + remove unpriced rows',
            f"Customer and Item tables merged onto the orders. {n1 - len(final_df):,} rows removed because the list price is "
            f"missing, or both base price and list price are 0 ({len(final_df):,} left).", rows=len(final_df), removed=n1 - len(final_df))

    # Step 1.5  data types: dates are real dates, numbers are numbers
    for c in ('Base Price', 'Quantity', 'List price'):
        final_df[c] = pd.to_numeric(final_df[c], errors='coerce')
    log.add(STAGE, '1.5', 'Data types', "Dates, quantities and prices converted to the correct types.", rows=len(final_df))

    # Step 1.6  clean the column names (Title Case)
    final_df.columns = final_df.columns.str.title()
    log.add(STAGE, '1.6', 'Column names', "Column names converted to Title Case (e.g. 'List price' → 'List Price').", rows=len(final_df))
    log.add(STAGE, '1.7', 'Cleaned_Sales', f"Cleaned sales table ready: {len(final_df):,} rows × {final_df.shape[1]} columns.", rows=len(final_df))
    return final_df
