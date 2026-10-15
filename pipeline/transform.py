"""Stage 2: Data Transformation & Feature Engineering  (notebooks/data_transformation.ipynb, steps 2.0 - 2.10)."""
import numpy as np
import pandas as pd

from pipeline.log import StepLog
from pipeline.schema import EARNED, LOSS, ON_GOING

STAGE = 'Stage 2 · Transformation'


def status_group(status):
    """Step 2.3: simplify the 6 sales-order statuses to Earned / On going / Loss (anything else = Other)."""
    s = pd.Series(status)
    return np.select([s.isin(EARNED), s.isin(ON_GOING), s.isin(LOSS)], ['Earned', 'On going', 'Loss'], default='Other')


def categorize_velocity(years):
    if years < 0.25:
        return 'Fast Moving (<3 Months)'
    elif years < 1.0:
        return 'Normal Velocity (3-12 Months)'
    elif years < 2.0:
        return 'Slow Moving (1-2 yrs)'
    elif years < 3.5:
        return 'High Aging Risk (2-3.5 yrs)'
    else:
        return 'Critical Risk! (>3.5 years)'


def transform(cleaned, log=None):
    """Return (df, inventory_features). df = the sales table with every engineered feature."""
    log = log if log is not None else StepLog()
    df = cleaned.copy()
    cols0 = df.shape[1]

    # 2.0 remove rows where Quantity is zero or negative
    n0 = len(df)
    df = df[df['Quantity'] > 0]
    log.add(STAGE, '2.0', 'Remove zero quantity', f"{n0 - len(df):,} rows with quantity ≤ 0 removed ({len(df):,} left).",
            rows=len(df), removed=n0 - len(df))

    # 2.1 time features
    df['Sales Order Date'] = pd.to_datetime(df['Sales Order Date'])
    df['Year'] = df['Sales Order Date'].dt.year
    df['Month'] = df['Sales Order Date'].dt.month
    df['Quarter'] = df['Sales Order Date'].dt.quarter
    df['is_month_end'] = df['Sales Order Date'].dt.is_month_end
    df['is_quarter_end'] = df['Sales Order Date'].dt.is_quarter_end
    df['Day of Week'] = df['Sales Order Date'].dt.day_of_week
    df['is_weekend'] = df['Sales Order Date'].dt.day_of_week >= 5
    df['Day of Month'] = df['Sales Order Date'].dt.day
    df['Year-Month'] = df['Sales Order Date'].dt.to_period('M')
    log.add(STAGE, '2.1', 'Time features', "Year, Month, Quarter, month/quarter end, day of week, weekend, day of month, Year-Month.", rows=len(df))

    # 2.2 financial features
    df['Total Sales Amount'] = df['Quantity'] * df['Base Price']
    df['Discount Amount'] = df['List Price'] - df['Base Price']
    df['Discount Percentage'] = (df['Discount Amount'] / df['List Price'])
    df['Total Gross Value'] = df['Quantity'] * df['List Price']
    df['Total Discount Value'] = df['Quantity'] * df['Discount Amount']
    df['Unit Selling Price'] = df['Total Sales Amount'] / df['Quantity']
    bins = [-np.inf, 1000, 10_000, 50_000, np.inf]                                  # in Baht
    labels = ['Small (<1k)', 'Medium (1k-10k)', 'Large (10k-50k)', 'Enterprise (>50k)']
    df['Order Size Tier'] = pd.cut(df['Total Sales Amount'], bins=bins, labels=labels)
    log.add(STAGE, '2.2', 'Financial features', "Total Sales Amount, Discount Amount / Percentage, Total Gross Value, "
            "Total Discount Value, Unit Selling Price, Order Size Tier (Small <1k · Medium · Large · Enterprise >50k Baht).", rows=len(df))

    # 2.2.8 customer history features
    df = df.sort_values(by=['Customer Internal Id', 'Sales Order Date'])
    df['Customer Cumulative Revenue'] = df.groupby('Customer Internal Id')['Total Sales Amount'].cumsum()
    df['Customer Order Count'] = df.groupby('Customer Internal Id').cumcount() + 1
    df['Customer AOV'] = df['Customer Cumulative Revenue'] / df['Customer Order Count']
    customer_ltv = df.groupby('Customer Internal Id')['Total Sales Amount'].sum().rename('Customer Total LTV')
    df = df.merge(customer_ltv, on='Customer Internal Id', how='left')
    log.add(STAGE, '2.2.8', 'Customer value', "Customer Cumulative Revenue, Order Count, Average Order Value and Total Lifetime Value.", rows=len(df))

    # 2.2.9 pricing flags
    df['is_discounted'] = df['Discount Amount'] > 0
    df['is_zero_base_price'] = df['Base Price'] == 0
    log.add(STAGE, '2.2.9', 'Discount flags', "is_discounted and is_zero_base_price flags.", rows=len(df))

    # 2.3 status group
    df['Sales Order Status Group'] = status_group(df['Sales Order Status'])
    g = df['Sales Order Status Group'].value_counts()
    log.add(STAGE, '2.3', 'Order status group', "Earned (Billed) · On going (pending billing) · Loss (pending fulfilment, partly fulfilled, closed): "
            + " · ".join(f"{k} {v:,}" for k, v in g.items()), rows=len(df))

    # 2.4 days since the customer's previous purchase
    df = df.sort_values(['Customer Internal Id', 'Sales Order Date'])
    df['Days Since Last Purchase'] = df.groupby('Customer Internal Id')['Sales Order Date'].diff().dt.days.fillna(0)
    log.add(STAGE, '2.4', 'Days since last purchase', "Days between a customer's consecutive orders.", rows=len(df))

    # 2.5 product-level demand
    df['Product-Level Demand'] = df.groupby('Item Code')['Quantity'].transform('mean')
    item_mean_price = df.groupby('Item Code')['Base Price'].transform('mean')
    df['Item Price Elasticity Ratio'] = np.where(item_mean_price > 0, df['Base Price'] / item_mean_price, 1.0)
    log.add(STAGE, '2.5', 'Product-level demand', "Average quantity per order for each item, and price relative to the item's average price.", rows=len(df))

    # 2.6 customer product diversity
    df['Customer Unique Item Count'] = df.groupby('Customer Internal Id')['Item Code'].transform(lambda x: (~x.duplicated()).cumsum())
    df['Customer Total Unique Items Overall'] = df.groupby('Customer Internal Id')['Item Code'].transform('nunique')
    log.add(STAGE, '2.6', 'Customer product diversity', "How many different items each customer has bought (so far, and overall).", rows=len(df))

    # 2.7 cyclical month
    df['sin_month'] = np.sin(2 * np.pi * df['Month'] / 12)
    df['cos_month'] = np.cos(2 * np.pi * df['Month'] / 12)
    log.add(STAGE, '2.7', 'Cyclical month', "sin_month and cos_month so December sits next to January.", rows=len(df))

    # 2.8 inventory features (one row per item)
    ref_date = df['Sales Order Date'].max()
    inv = df.groupby(['Item Internal Id', 'Item Code']).agg(
        Last_Sale_Date=('Sales Order Date', 'max'), First_Sale_Date=('Sales Order Date', 'min'),
        Total_Unit_Sold=('Quantity', 'sum'), Total_Revenue=('Total Sales Amount', 'sum'),
        Order_Count=('So Internal Id', 'count')).reset_index()
    inv['Days_Since_Last_Sale'] = (ref_date - inv['Last_Sale_Date']).dt.days
    inv['Years_Inactive'] = inv['Days_Since_Last_Sale'] / 365.25
    inv['Inventory_Risk_Tier'] = inv['Years_Inactive'].apply(categorize_velocity)
    inv['Days_Active'] = (ref_date - inv['First_Sale_Date']).dt.days.clip(lower=1)
    inv['Sales_Frequency_Ratio_Units'] = inv['Total_Unit_Sold'] / inv['Days_Active']
    inv['Sales_Frequency_Ratio_Orders'] = inv['Order_Count'] / inv['Days_Active']
    log.add(STAGE, '2.8', 'Inventory features', f"{len(inv):,} items: days since last sale, risk tier (Fast Moving … Critical Risk), "
            "units and orders per active day.", rows=len(inv))

    # 2.9 outlier capping
    for col in ['Quantity', 'Total Sales Amount', 'Base Price']:
        upper_limit = df[col].quantile(0.99)
        lower_limit = df[col].quantile(0.001)
        df[f'{col}_Capped'] = df[col].clip(lower=lower_limit, upper=upper_limit)
    log.add(STAGE, '2.9', 'Outliers', "Quantity, Total Sales Amount and Base Price capped at the 99th / 0.1th percentile "
            "(new *_Capped columns; no rows removed).", rows=len(df))
    log.add(STAGE, '2.10', 'Transformed data', f"{len(df):,} rows × {df.shape[1]} columns ({df.shape[1] - cols0} new features).", rows=len(df))
    return df, inv
