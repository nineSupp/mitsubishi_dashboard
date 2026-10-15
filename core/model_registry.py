"""Single source of truth for 'which model/method powers which dashboard feature'.
Pure Python (no Streamlit) so the views, the model map and the accuracy table all read the same facts."""

# Methods that are actually used in the dashboard
METHODS = {
    'gbm': dict(
        name='Gradient Boosting', kind='Machine learning', icon='🧠',
        how='Learns from the last 3 months, their average and the month of the year (seasonality) of company revenue.',
        eval_name='Gradient Boosting (lags + seasonality) [dashboard v1]', eval_level='Company x month'),
    'mix': dict(
        name='Sales-mix allocation', kind='Statistical rule', icon='📐',
        how="Splits the Gradient Boosting company total across categories and items by each item's last-12-month sales mix.",
        eval_name='Top-down: company GBM + flat-average mix', eval_level='Category x month'),
    'abcxyz': dict(
        name='ABC × XYZ classification', kind='Rule-based', icon='🧮',
        how='A/B/C from cumulative 12-month revenue (80% / 95% cut-offs). X/Y/Z from demand variability (coefficient of variation).',
        eval_name=None, eval_level=None),
    'safety': dict(
        name='Safety-stock formula', kind='Statistics', icon='📦',
        how='Safety stock = z × monthly demand std × √lead time. Reorder point = demand over lead time + safety stock.',
        eval_name=None, eval_level=None),
    'flags': dict(
        name='Slow / dead-stock rules', kind='Rule-based', icon='🚦',
        how='Flags items by months since last sale (6-11 slow, 12+ none) and by discontinued / to-be-advised status.',
        eval_name=None, eval_level=None),
    'growth': dict(
        name='Fiscal-year growth', kind='Descriptive statistics', icon='📈',
        how='Year-on-year change and compound annual growth of realised revenue, FY2021 to FY2024.',
        eval_name=None, eval_level=None),
    'descriptive': dict(
        name='Descriptive analytics', kind='No model', icon='📊',
        how='Totals, shares, averages and trends calculated directly from your orders (no prediction).',
        eval_name=None, eval_level=None),
    'scenario': dict(
        name='Scenario arithmetic', kind='Assumption-driven', icon='🎛️',
        how='Applies your price, discount, demand, customer and new-item assumptions to the baseline forecast, in that order.',
        eval_name=None, eval_level=None),
    'dataload': dict(
        name='Data checks', kind='Rule-based', icon='🧾',
        how='Checks columns, dates, quantities, prices and rows already in the dashboard before anything is saved.',
        eval_name=None, eval_level=None),
    'p_clean': dict(
        name='Stage 1 · Cleaning', kind='Rule-based', icon='🧹',
        how='Strips column names, removes exact duplicate rows, joins customer and item details, and drops rows with no usable list price.',
        eval_name=None, eval_level=None),
    'p_features': dict(
        name='Stage 2 · Feature engineering', kind='Rule-based', icon='🛠️',
        how='Removes zero quantities, then builds 33 features: time, discount and value, customer history, product demand, inventory risk, order status group.',
        eval_name=None, eval_level=None),
    'p_encode': dict(
        name='Stage 3 · Encoding', kind='Rule-based', icon='🔢',
        how='Turns categories into numbers for modelling: ordered tiers, frequency counts and yes/no columns.',
        eval_name=None, eval_level=None),
    'backtest': dict(
        name='Rolling backtest (WAPE)', kind='Evaluation', icon='🎯',
        how='Trains only on earlier months, forecasts a full year, then scores against what really happened.',
        eval_name=None, eval_level=None),
}

# Dashboard feature -> [(method key, what it does on that page)]
FEATURES = {
    'forecast': dict(title='Sales Forecast', models=[
        ('gbm', 'company revenue by month (FY2025)'),
        ('mix', 'category and item forecasts')]),
    'inventory': dict(title='Inventory Management', models=[
        ('mix', 'forecast demand per item'),
        ('abcxyz', 'priority classes'),
        ('safety', 'safety stock and reorder point'),
        ('flags', 'slow and dead stock')]),
    'growth': dict(title='Product & Category Growth', models=[
        ('growth', 'FY2021-FY2024 growth and CAGR'),
        ('mix', 'FY2025 outlook per category')]),
    'accuracy': dict(title='Model Accuracy', models=[
        ('backtest', 'scores every candidate against real results')]),
    'whatif': dict(title='What-If Scenarios', models=[
        ('scenario', 'turns your assumptions into revenue and units'),
        ('gbm', 'baseline company forecast'),
        ('mix', 'baseline per category'),
        ('safety', 'inventory what-if (safety stock, reorder point)')]),
    'upload': dict(title='Add New Data', models=[
        ('dataload', 'validates and stores your file'),
        ('gbm', 'retrains the company forecast on history + your data'),
        ('mix', 're-splits the new forecast by category and item')]),
    'import': dict(title='Import & Process Data', models=[
        ('p_clean', 'cleans your raw Customer, Item and Sale Order files'),
        ('p_features', 'builds the engineered features'),
        ('p_encode', 'encodes the categories and writes the dataset')]),
    'products': dict(title='Product Performance', models=[('descriptive', 'item and category rankings')]),
    'customers': dict(title='Customers', models=[('descriptive', 'customer value, concentration and activity')]),
    'industries': dict(title='Industries', models=[('descriptive', 'revenue and growth by industry')]),
    'orders': dict(title='Orders', models=[('descriptive', 'order size, timing and status mix')]),
}

# The team's four quantity-forecasting models (descriptions from the team slide "Quantity Forecasting: Machine Learning Models")
TEAM_MODELS = [
    dict(name='RandomForest', eval='RandomForest (recursive)', mix='Top-down: company GBM + RandomForest mix', config='random_forest',
         desc="Combines multiple decision trees to produce stable predictions. Suitable for sales data because it can capture nonlinear "
              "relationships among historical sales, product, seasonal and customer-related features."),
    dict(name='LightGBM', eval='LightGBM (recursive, Tweedie)', mix='Top-down: company GBM + LightGBM mix', config='lightgbm',
         desc="Uses fast gradient boosting to learn complex demand patterns. Its Tweedie objective is suitable for our data because "
              "many products have zero-demand months."),
    dict(name='XGBoost', eval='XGBoost (recursive, Tweedie)', mix='Top-down: company GBM + XGBoost mix', config='xgboost',
         desc="Uses gradient boosting with regularization to predict demand while controlling model complexity. It captures nonlinear "
              "relationships and gives another boosting-based approach for comparison."),
    dict(name='Hurdle (TwoStage)', eval='Hurdle two-stage (recursive)', mix='Top-down: company GBM + Hurdle mix', config='hurdle',
         desc="Splits forecasting into two steps: whether a product will sell and how much it will sell if purchased. This matches our "
              "data because many products have intermittent or zero-demand periods."),
]

# Candidates that were tested but are NOT used, with the reason (eval names -> reason)
TESTED_ONLY = {
    'Ridge (trend + seasonality) [dashboard v1]': 'less accurate than Gradient Boosting on FY2024',
    'Seasonal naive [dashboard v1]': 'simple benchmark',
    'Seasonal naive x latest growth': 'simple benchmark',
    'Seasonal naive (same month last year)': 'simple benchmark',
    'Flat 12-month average': 'benchmark; its mix is used inside the sales-mix allocation',
    'Seasonal average (12m avg x category seasonality)': 'benchmark',
    'HGB log-target, recursive': 'tiny edge at item-month level, but totals do not add up to category/company',
    'HGB Poisson, recursive': 'weaker than simple averages at category level',
    'HGB Poisson, direct multi-horizon': 'weaker than simple averages at category level',
    'RandomForest (recursive)': "team model; below simple averages at company and category level (see team-model table)",
    'Hurdle two-stage (recursive)': "team model; below simple averages at company and category level (see team-model table)",
    'LightGBM (recursive, Tweedie)': "team model; scored only when lightgbm is installed (run scripts.evaluate_models)",
    'XGBoost (recursive, Tweedie)': "team model; scored only when xgboost is installed (run scripts.evaluate_models)",
    'Blend: HGB Poisson recursive + flat average': 'no gain over the flat average',
    'Top-down: company GBM + HGB Poisson mix': 'same company total, slightly worse category split',
    'Top-down: company GBM + HGB log-target mix': 'same company total, worse category split in validation',
    'Top-down: company GBM + RandomForest mix': 'team model as splitter: lower category accuracy than the flat mix in validation',
    'Top-down: company GBM + Hurdle mix': 'team model as splitter: lower category accuracy than the flat mix in validation',
    'Top-down: company GBM + LightGBM mix': 'team model as splitter; scored only when lightgbm is installed',
    'Top-down: company GBM + XGBoost mix': 'team model as splitter; scored only when xgboost is installed',
    'SARIMA (log) [friend]': "shared-project design (only runs if statsmodels is installed)",
}


def used_for(eval_name):
    """Where a tested model is used in the dashboard ('' if it is tested only)."""
    for key, m in METHODS.items():
        if m['eval_name'] == eval_name:
            if key == 'gbm':
                return 'Sales Forecast: company total (feeds Growth and Inventory)'
            if key == 'mix':
                return 'Category and item split (Sales Forecast, Inventory, Growth)'
    return ''
