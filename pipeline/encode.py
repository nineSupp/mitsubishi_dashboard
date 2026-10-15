"""Stage 3: Data Encoding for categorical data  (notebooks/data_encode.ipynb, steps 3.1 - 3.3)."""
import pandas as pd

from pipeline.log import StepLog

STAGE = 'Stage 3 · Encoding'
ORDER_TIER_MAP = {'Small (<1k)': 1, 'Medium (1k-10k)': 2, 'Large (10k-50k)': 3, 'Enterprise (>50k)': 4}
INVENTORY_RISK_MAP = {"Fast Moving (<3 Months)": 1, "Normal Velocity (3-12 Months)": 2, "Slow Moving (1-2 yrs)": 3,
                      "High Aging Risk (2-3.5 yrs)": 4, "Critical Risk! (>3.5 years)": 5, "Unknown": 0}
OHE_COLUMNS = ['Customer Type', 'Production Status', 'Sales Order Status Group', 'Product Category 1', 'Fa Sub Industries']
DROP_COLUMNS = ["Sales Order Status", "Company Name", "Product Category 2", "Year-Month", "Order Size Tier", "Inventory_Risk_Tier"]


def encode(df_sales, df_inv, log=None):
    """Return the final machine-learning-ready dataset (final_dataset_main)."""
    log = log if log is not None else StepLog()

    # 3.1 merge the inventory context into every transaction
    inv_cols = ['Item Internal Id', 'Days_Since_Last_Sale', 'Inventory_Risk_Tier', 'Sales_Frequency_Ratio_Units',
                'Sales_Frequency_Ratio_Orders']
    df_inv_subset = df_inv.rename(columns={'Item Internal ID': 'Item Internal Id'})[inv_cols]
    df = pd.merge(df_sales, df_inv_subset, on='Item Internal Id', how='left')
    df['Inventory_Risk_Tier'] = df['Inventory_Risk_Tier'].fillna('Unknown')
    log.add(STAGE, '3.1', 'Merge inventory context', f"Item-level inventory features joined to {len(df):,} order lines.", rows=len(df))

    # 3.2.1 ordinal encoding
    df['Order_Size_Tier_Encoded'] = df['Order Size Tier'].map(ORDER_TIER_MAP).fillna(0)
    df['Inventory_Risk_Tier_Encoded'] = df['Inventory_Risk_Tier'].map(INVENTORY_RISK_MAP).fillna(0)
    log.add(STAGE, '3.2.1', 'Ordinal encoding', "Order size tier 1-4 and inventory risk tier 0-5 (keeps the order).", rows=len(df))

    # 3.2.2 frequency encoding
    df['Customer_Order_Frequency'] = df.groupby('Customer Internal Id')['Customer Internal Id'].transform('count')
    df['Item_Order_Frequency'] = df.groupby('Item Code')['Item Code'].transform('count')
    log.add(STAGE, '3.2.2', 'Frequency encoding', "How often each customer / item appears.", rows=len(df))

    # 3.2.3 one-hot encoding
    n_before = df.shape[1]
    df_encode = pd.get_dummies(df, columns=OHE_COLUMNS, drop_first=True, dtype=int)
    log.add(STAGE, '3.2.3', 'One-hot encoding', f"{', '.join(OHE_COLUMNS)} → {df_encode.shape[1] - n_before + len(OHE_COLUMNS)} yes/no columns "
            "(the first category of each is the baseline).", rows=len(df_encode))

    # 3.3 final clean-up
    df_final = df_encode.drop(columns=[c for c in DROP_COLUMNS if c in df_encode.columns])
    log.add(STAGE, '3.3', 'Final dataset', f"{len(df_final):,} rows × {df_final.shape[1]} columns ready (final_dataset_main).", rows=len(df_final))
    return df_final
