# Mitsubishi Electric x TNIC Team 6: Sales Forecast & Inventory Dashboard

## How to launch the dashboard
1. **Windows:** double-click `Start_Dashboard.bat`.
   The first run downloads everything it needs (2-5 minutes, internet needed, once only) and then opens the dashboard in your browser.
   It also creates a shortcut called **Mitsubishi TNIC Dashboard** (with the Mitsubishi icon) in this folder. Use the shortcut next time.
   Want it on the desktop? Double-click `Create_Desktop_Shortcut.bat`.
   **Mac:** double-click `start_dashboard.command` (first time: right-click > Open).
2. **Get the data in** (the final dataset file is too large for GitHub, so it is on Google Drive). Either:
   * **Option 1 · download the ready dataset:** get `final_dataset_main.csv` from
     `https://drive.google.com/drive/folders/1ALNk8cdzmvdQcQVyC5cI3fX7Y3MUmTv1?usp=sharing`
     and put it in the `data/` folder (next to `TNIC Data_2025.xlsx`), then reload the page.
   * **Option 2 · import the raw files:** if `final_dataset_main.csv` is missing, the dashboard opens a welcome screen.
     Drop the raw **Customer**, **Item** and **Sale Order History** files there (Excel or CSV). The dashboard cleans, transforms and
     encodes them for you and creates the dataset itself. See "Import & process data" below.

Requirements: **64-bit Python 3.10 to 3.13** (3.12 recommended; **not** 3.14 or newer, which have no ready-made packages and fail with "Failed to build pyarrow").
If no suitable Python is found, the launcher offers to install Python 3.12 for you. `.streamlit/config.toml` hides Streamlit's Deploy button.

## What the dashboard does
One page. Click a question card to drill down; **← Overview** goes back.

| Card | Answers | Drill-down levels |
|---|---|---|
| Sales Forecast | FY2025 forecast with a low-high range (switch on "compare" to see the real results) | company → category → item |
| Inventory Management | what to stock, safety stock, slow/dead stock (as of Mar 2025) | ABC×XYZ → reorder planner → slow/dead lists → stock on hand → back-check vs real FY2025 |
| Product & Category Growth | YoY and CAGR FY2021-FY2024, FY2025 forecast per category | category → items growing/declining |
| Model Accuracy | rolling backtest of every candidate model, your team's four quantity models | by level, by category, by model |
| What-If Scenarios | revenue, units and inventory under your assumptions | sales tab → inventory tab |
| Add New Data | upload new orders, check, include and retrain | upload → added files → update forecast |
| Import & Process Data | clean, transform and encode the raw files | upload → process → report |

"More analysis" buttons open Products, Customers, Industries and Orders. Charts marked "Click a bar or point to drill down" are interactive.
The Main Panel (sidebar) filters the Overview and those pages; **↺ Reset filters** restores the original values.
Money is shown in Thai Baht (฿).

## Import & process data (the notebook pipeline, built into the dashboard)
The three notebooks in `notebooks/` are ported step by step into the `pipeline/` package, so the dashboard can do all the preparation itself:

| Stage | Notebook | Module | What it does |
|---|---|---|---|
| 1 · Cleaning | `clean_data.ipynb` | `pipeline/clean.py` | strips column names, removes exact duplicate rows, joins customer and item details, drops rows with no usable list price, fixes types and column names |
| 2 · Transformation | `data_transformation.ipynb` | `pipeline/transform.py` | removes zero quantities; builds time, discount/value, customer-history, product-demand, inventory-risk and order-status features; caps outliers |
| 3 · Encoding | `data_encode.ipynb` | `pipeline/encode.py` | merges inventory context, ordinal / frequency / one-hot encoding, final clean-up |

* Open **Import & Process Data** (home page card), drop the files, press the button. A step-by-step report shows what each step did and how many rows it removed.
* Output: `data/final_dataset_main.csv` (the dataset the dashboard reads), `data/processed/item_master.csv`, `customer_master.csv` and `processing_report.json`.
* The files can be separate (Customer, Item, Sale Order History) or one workbook with three sheets (like `TNIC Data_2025.xlsx`). The dashboard finds out which table is which.
* The same cleaning rules are applied to the FY2025 results file and to files added on the **Add New Data** page, so every number is on one consistent footing.
* `tests/test_pipeline.py` runs YOUR notebook code and the ported pipeline on the same input and checks the output is identical at every stage.
* If you import data that differs from the original, use **Rebuild the forecasts** on the same page (about 2 minutes); accuracy tables refresh with `python -m scripts.evaluate_models`.
* Details: `docs/DATA_PIPELINE.md`.

## How training and testing work
* **The dashboard's data is FY2021-FY2024 only.** `TNIC Data_2025.xlsx` is never merged into it: its FY2025 orders are the *real results* used only to compare with the forecast (cleaned with the same rules). Its Item/Company sheets provide the categories and industries.
* **Stage 1, validation (history only):** train FY2021-22 → test FY2023; train FY2021-23 → test FY2024. Models are ranked here.
* **Stage 2, final test:** train FY2021-FY2024 → forecast FY2025 → compare with the real FY2025 orders.
* FY = April to March. Revenue = Base Price x Quantity, Closed ("Loss") orders excluded (`FORECAST_EXCLUDE_STATUS` in `config.py`).

## Which model powers what
The same table is on the home page and the Model Accuracy page. Every page has a dark "Models on this page" banner with each model's description, what it does there, and its accuracy (or a back-check where there is no forecast). It is defined in `core/model_registry.py`.

| Feature | Model / method |
|---|---|
| Sales Forecast, company total | Gradient Boosting (ML) |
| Sales Forecast, categories and items | Sales-mix allocation of the company forecast |
| Inventory | sales-mix demand, ABC×XYZ rules, safety-stock formula, slow-stock rules |
| Product & Category Growth | fiscal-year YoY and CAGR (history), sales-mix allocation (FY2025 outlook) |
| Import & Process Data | the three-stage cleaning pipeline |
| Model Accuracy | rolling backtest, WAPE |

Your team's RandomForest, LightGBM, XGBoost and Hurdle models are tested too (Model Accuracy page). To use one as the splitter of the company forecast set `ITEM_MIX_MODEL` in `config.py` (`random_forest`, `lightgbm`, `xgboost`, `hurdle`; default `flat`). LightGBM and XGBoost need `pip install lightgbm xgboost` and a run of `python -m scripts.evaluate_models` to get their scores.

## Manual setup (without the launcher)
```
pip install -r requirements.txt
streamlit run app.py
```
Logo files go in `assets/img/` (`mitsu_logo2.png`, `mitsu_icon_logo.png`, `mitsu_icon_logo.ico`). Without them the header shows text.
Optional refreshes: `python -m scripts.train_forecasts` (forecasts, inventory table, run info in `outputs/`, already included) and `python -m scripts.evaluate_models --fold FY2023`, `--fold FY2024`, `--fold FY2025`, then `--combine` (accuracy tables).

## Folders
```
app.py                    entry point (page config, theme, first-run welcome screen, filters, router)
config.py                 paths, brand colours, team members, currency, Drive link, ITEM_MIX_MODEL
Start_Dashboard.bat       one-click launcher (Windows); creates the shortcut with the Mitsubishi icon
Create_Desktop_Shortcut.bat  puts the same shortcut on the desktop
start_dashboard.command   launcher for Mac
assets/                   theme.css (original theme), extra.css (cards, buttons), js, img (logos, .ico)
pipeline/                 the three notebook stages ported: clean.py, transform.py, encode.py, readers.py, run.py
notebooks/                the original notebooks (clean_data, data_transformation, data_encode, EDA)
core/                     data loading, sidebar filters, cached loaders, analytics, model registry and metrics
forecasting/              item model, series models, evaluation, official pipeline, live retraining, scenarios
scripts/                  evaluate_models.py (backtest), train_forecasts.py (writes outputs/)
ui/                       theme injection, KPI cards, chart helpers, drill-down navigation, model panels
views/                    one file per card / detail view (incl. import_data.py)
outputs/                  generated CSVs read by the dashboard
docs/                     PRESENTATION_GUIDE.md, DATA_PIPELINE.md
tests/                    smoke_views, test_interactions, test_models, test_pipeline, test_import
```

## Limits
* No stock levels or supplier lead times in the data: safety stock uses the lead time and service level you set; upload stock on hand for money at risk.
* No product launch date: "older than 5 years" cannot be measured; months since last sale is the proxy.
* Items with no list price (mostly brand-new products) are removed by the cleaning rules, as in the original dataset, so their sales are not in the numbers.
* The shared project's VIP 37% discount and partial-order price cut are NOT applied (they are not in `Total Sales Amount`).
