"""Read raw files (Excel or CSV) and work out which one is the Sale Order History, Customer or Item table."""
import pandas as pd

from pipeline.schema import EXPECTED, OPTIONAL, ROLE_NAMES, key


def detect_role(columns):
    """Return 'orders' | 'customers' | 'items' | None from a list of column names."""
    k = {key(c) for c in columns}
    if {'salesordernumber', 'quantity', 'baseprice', 'itemcode'} <= k:
        return 'orders'
    if {'itemcode', 'productcategory1'} <= k:
        return 'items'
    if 'customertype' in k or 'fasubindustries' in k:
        return 'customers'
    return None


def _is_excel(name):
    return str(name).lower().endswith(('.xlsx', '.xlsm', '.xls'))


def load_tables(files, roles=None):
    """files: list of (file_name, file_or_path). Excel workbooks may hold several tables (one per sheet).
    roles limits which tables are read (default all three).
    Returns (tables, found, problems): tables = {role: DataFrame}, found = [(role, source label, rows)]."""
    wanted = tuple(roles) if roles else tuple(EXPECTED)
    tables, found, problems = {}, [], []
    for name, src in files:
        try:
            if _is_excel(name):
                xl = pd.ExcelFile(src)
                for sheet in xl.sheet_names:
                    role = detect_role(xl.parse(sheet, nrows=3).columns)
                    if role in wanted and role not in tables:
                        tables[role] = xl.parse(sheet)
                        found.append((role, f"{name} · sheet '{sheet}'", len(tables[role])))
            else:
                role = detect_role(pd.read_csv(src, nrows=3).columns)
                if hasattr(src, 'seek'):
                    src.seek(0)
                if role in wanted and role not in tables:
                    tables[role] = pd.read_csv(src)
                    found.append((role, name, len(tables[role])))
                elif role is None:
                    problems.append(f"{name}: could not tell which table this is (columns not recognised).")
        except Exception as e:                                       # noqa: BLE001
            problems.append(f"{name}: could not be read ({e}).")
    for role in wanted:
        if role not in tables:
            problems.append(f"Missing the {ROLE_NAMES[role]} table.")
    return tables, found, problems


def canonicalise(df, role):
    """Strip whitespace from column names (Step 1.1) and rename columns to the standard names.
    Returns (frame, missing_required_columns)."""
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    by_key = {key(c): c for c in df.columns}
    rename, missing = {}, []
    for std in EXPECTED[role]:
        src = by_key.get(key(std))
        if src is None:
            if std not in OPTIONAL[role]:
                missing.append(std)
        elif src != std:
            rename[src] = std
    return df.rename(columns=rename), missing
