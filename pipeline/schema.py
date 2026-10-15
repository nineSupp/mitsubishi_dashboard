"""Raw-table definitions shared by the readers and the stages."""
import re

# Columns the three raw tables must have (names are matched ignoring case, spaces and punctuation)
ORDER_COLUMNS = ['SO Internal ID', 'Sales Order Date', 'Sales Order Number', 'Sales Order Status', 'Customer Internal ID',
                 'Company Name', 'Item Internal ID', 'Item Code', 'Base Price', 'Quantity']
CUSTOMER_COLUMNS = ['Customer Internal ID', 'Company Name', 'Customer Type', 'FA Sub Industries']
ITEM_COLUMNS = ['Item Internal ID', 'Item Code', 'Production Status', 'Product Category 1', 'Product Category 2', 'List price']
EXPECTED = {'orders': ORDER_COLUMNS, 'customers': CUSTOMER_COLUMNS, 'items': ITEM_COLUMNS}
OPTIONAL = {'orders': {'SO Internal ID'}, 'customers': set(), 'items': set()}      # synthesised if missing
ROLE_NAMES = {'orders': 'Sale Order History', 'customers': 'Customer', 'items': 'Item'}

# Sales-order status grouping (Step 2.3 of the notebook)
EARNED = ['Billed']
ON_GOING = ['Pending Billing', 'Pending Billing/Partially Fulfilled']
LOSS = ['Pending Fulfillment', 'Partially Fulfilled', 'Closed']


def key(name):
    """'Customer Internal ID ' -> 'customerinternalid' (case, spaces and punctuation ignored)."""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())
