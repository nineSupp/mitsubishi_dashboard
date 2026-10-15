# Data pipeline: from raw files to the dashboard dataset

The three Jupyter notebooks (`notebooks/`) are ported one-to-one into the `pipeline/` package. The code lives in
`.py` files so the dashboard (and the command line, and the tests) can run it without Jupyter.

```
Customer + Item + Sale Order History  (raw, Excel or CSV)
        │
        ▼  Stage 1 · Cleaning            pipeline/clean.py        ← clean_data.ipynb
        │     1.1 load, strip column names           1.4 merge customer + item, drop unpriced rows
        │     1.3 remove exact duplicate rows        1.5 data types      1.6 Title-Case column names
        ▼  Stage 2 · Transformation      pipeline/transform.py    ← data_transformation.ipynb
        │     2.0 remove quantity ≤ 0       2.1 time features        2.2 financial features (discount, gross value, order size tier)
        │     2.2.8 customer history        2.3 order status group   2.4 days since last purchase
        │     2.5 product demand            2.6 customer diversity   2.7 cyclical month
        │     2.8 inventory features (one row per item)              2.9 outlier caps
        ▼  Stage 3 · Encoding            pipeline/encode.py       ← data_encode.ipynb
        │     3.1 merge inventory context   3.2 ordinal / frequency / one-hot encoding   3.3 final clean-up
        ▼
data/final_dataset_main.csv   (what the dashboard reads)
```

## Rules worth knowing (they decide which rows survive)
* **Exact duplicate rows** in Sale Order History are removed (Step 1.3).
* **Unpriced rows** are removed: the item has no list price in the Item table, or both base price and list price are 0 (Step 1.4).
  New products that are not priced yet therefore never reach the dataset.
* **Quantity ≤ 0** is removed (Step 2.0).
* **Order status group:** Earned = Billed · On going = Pending Billing, Pending Billing/Partially Fulfilled ·
  Loss = Pending Fulfillment, Partially Fulfilled, Closed. The dashboard shows Earned as "Completed", and leaves Loss out of revenue.
* Money amounts are in Baht.

## Accepted input
* Three tables: **Sale Order History** (SO Internal ID, Sales Order Date, Sales Order Number, Sales Order Status, Customer Internal ID,
  Company Name, Item Internal ID, Item Code, Base Price, Quantity), **Customer** (Customer Internal ID, Company Name, Customer Type,
  FA Sub Industries) and **Item** (Item Internal ID, Item Code, Production Status, Product Category 1, Product Category 2, List price).
* Excel or CSV, as separate files or as sheets of one workbook. Column names are matched ignoring case, spaces and punctuation.
  Dates can be real dates, text or Excel date numbers. A missing `SO Internal ID` is generated.

## How we know it matches the notebooks
`python -m tests.test_pipeline` runs the notebook code itself (`tests/reference_from_notebooks.py` extracts the processing cells from
`notebooks/*.ipynb`) and the ported pipeline on the same raw tables, then compares the cleaned table, the transformed table, the
inventory features and the final encoded dataset. All four are identical, with the same columns in the same order.

## Command line (no dashboard)
```
python - <<'PY'
from pipeline import load_tables, run_pipeline, write_outputs
tables, found, problems = load_tables([("Customer.xlsx", "Customer.xlsx"), ("Item.xlsx", "Item.xlsx"), ("Sale Order History.xlsx", "Sale Order History.xlsx")])
result = run_pipeline(tables["customers"], tables["items"], tables["orders"])
write_outputs(result, "data")
PY
```
