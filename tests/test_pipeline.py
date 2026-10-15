"""The ported pipeline must give exactly what the notebooks give, stage by stage, on the same input.
    python -m tests.test_pipeline"""
import sys
import time

import numpy as np
import pandas as pd

from pipeline import run_pipeline
from tests.reference_from_notebooks import run_notebooks

from tests._paths import workbook
XLSX = workbook()
ok = True


def check(name, cond, extra=''):
    global ok
    ok &= bool(cond)
    print('OK  ' if cond else 'FAIL', name, extra)


def same(a, b, name):
    try:
        a2, b2 = a.reset_index(drop=True), b.reset_index(drop=True)
        pd.testing.assert_frame_equal(a2, b2, check_dtype=False, check_exact=False, rtol=1e-9, atol=1e-9)
        check(name, True, f'{a.shape}')
    except AssertionError as e:
        check(name, False, str(e)[:300])


raw = pd.read_excel(XLSX, sheet_name=None)
orders_raw, customers_raw, items_raw = raw['FY25 - Sale Order History'], raw['Company'], raw['Item']
orders_dates = orders_raw.copy()                                   # what a clean raw file looks like: real dates
orders_dates['Sales Order Date'] = pd.to_datetime(orders_dates['Sales Order Date'], unit='D', origin='1899-12-30')

ref = run_notebooks(customers_raw, items_raw, orders_dates)       # YOUR notebook code
t = time.time()
mine = run_pipeline(customers_raw, items_raw, orders_raw)         # ported code, raw Excel serial dates
print(f'ported pipeline: {time.time() - t:.1f}s,', mine.summary)

same(mine.cleaned, ref['cleaned'], 'Stage 1 cleaned table equals clean_data.ipynb')
same(mine.transformed.drop(columns=['Year-Month']), ref['transformed'].drop(columns=['Year-Month']), 'Stage 2 transformed table equals data_transformation.ipynb')
check('Stage 2 Year-Month equal', (mine.transformed['Year-Month'].astype(str).values == ref['transformed']['Year-Month'].astype(str).values).all())
same(mine.inventory, ref['inventory'], 'Stage 2 inventory features equal')
same(mine.final, ref['final'], 'Stage 3 final dataset equals data_encode.ipynb')
check('same column names and order', list(mine.final.columns) == list(ref['final'].columns))

# the same input as CSV files and as real dates must give the same answer
as_csv = run_pipeline(customers_raw, items_raw, orders_dates)
same(as_csv.final, mine.final, 'real dates and Excel date numbers give the same dataset')

# messy headers are fixed by the strip / canonicalise step
messy = orders_raw.rename(columns={'Quantity': ' quantity ', 'Base Price': 'BASE PRICE'})
same(run_pipeline(customers_raw, items_raw, messy).final, mine.final, 'messy column names are tolerated')

# clear errors for bad input
try:
    run_pipeline(customers_raw, items_raw, orders_raw.drop(columns=['Quantity']))
    check('missing column raises a clear error', False)
except ValueError as e:
    check('missing column raises a clear error', 'Quantity' in str(e), str(e)[:80])

# the step log
steps = mine.log.table()
check('step log covers all three stages', set(steps['stage']) == {'Stage 1 · Cleaning', 'Stage 2 · Transformation', 'Stage 3 · Encoding'})
print(steps[['step', 'title', 'rows']].to_string(index=False))
sys.exit(0 if ok else 1)
