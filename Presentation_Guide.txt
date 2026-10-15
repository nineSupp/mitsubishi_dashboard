# Presentation guide: Mitsubishi Electric x TNIC Sales & Inventory Dashboard (Team 6)

All amounts are in Thai Baht (฿). FY = fiscal year, April to March (FY2025 = Apr 2025 to Mar 2026).
Every number below comes from the data or from the saved model results (`outputs/`). Nothing is estimated by hand.

---------------------------------------------------------------------------------------------------

## 1. The 60-second story

1. We have four fiscal years of order history (FY2021 to FY2024): 265,070 order lines, 5,693 items, 2,159 customers.
2. **Question 1, sales:** how much will we sell in FY2025? Our model said **฿1,981M**. The real result (from `TNIC_Data_2025.xlsx`, cleaned with the same rules) was **฿1,981M**: the full-year total was off by 0.04%, and the monthly shape was 87% accurate.
3. **Question 2, inventory:** which items deserve stock and which are dead weight? As of March 2025, 2,410 items had not sold for 12+ months, while only 455 "A" items produced 80% of revenue.
4. **Question 3, growth:** PLC is 43.5% of revenue; the four big categories (PLC, INV, SV, HMI) are 91.5%.
5. **Question 4, trust:** every model was tested only on years it had not seen. We say where it is good (company totals) and where it is weak (single items by month, category growth direction).
6. Three tools: **What-If** (change price, discount, demand, lost customers, lead time), **Add New Data** (upload orders, retrain) and **Import & Process Data** (drop the raw files; the dashboard cleans and prepares them).

---------------------------------------------------------------------------------------------------

## 2. Definitions you must know

| Term | Meaning |
|---|---|
| Revenue | Base price x quantity of an order line |
| Realised revenue | Revenue **excluding Loss orders**. Loss = Closed + Pending Fulfillment + Partially Fulfilled (never shipped or billed). They are about 19% of order value in the history |
| FY | April to March. FY2024 = Apr 2023 to Mar 2024 |
| WAPE | Total absolute error divided by total actual. **Accuracy = 1 − WAPE** |
| Validation | Testing on years the model did not train on, using history only (FY2023, FY2024). Used to choose models |
| Final test | Train on FY2021-FY2024, forecast FY2025, compare with the real FY2025 orders. Never used for training |
| Range (~80%) | Low and high band around a forecast: the real value should fall inside about 8 months out of 10 |
| Cleaned | Passed through the same three-stage pipeline as the history (duplicates, unpriced rows, status groups) |

---------------------------------------------------------------------------------------------------

## 3. Business insights (what we found)

**Revenue trend (realised, ฿ million):** FY2021 2,421 → FY2022 2,641 (+9.1%) → FY2023 1,772 (**−32.9%**) → FY2024 1,997 (+12.7%) → FY2025 1,981 (−0.8%, real result).
The FY2023 drop is the biggest event in the data. No model predicted it, and the data has no cause for it. Say so honestly. After the rebound, FY2024 and FY2025 are flat.

**Product mix (FY2024):** PLC 43.5%, INV 16.8%, SV 16.4%, HMI 14.8%. Together 91.5%. The small categories matter little for revenue.
Growth FY2023→FY2024: PLC +19.6%, INV +15.5%, SV +23.3%, HMI +21.8%; Robot −58.1% and iQSS −53.4% (both small).

**Customer concentration (FY2024):** 821 active customers, but the top 10 give 68.8% of revenue and just 19 customers give 80%.
The 10 VIP customers give 64.2%. Losing one big account would be felt (use What-If → "Lose the top 3 customers").

**Industry concentration:** Wholesale and Distribution is 73.5% of FY2024 revenue.

**Item concentration:** 456 of 3,129 active items (14.6%) make 80% of FY2024 revenue.

**Discounting:** 81% of order lines carry a discount. Average depth fell from 28.1% of list value (FY2021) to 25.1%, 16.3%, then 16.1% (FY2024). Revenue fell in the same period as the discount cut in FY2023; the data cannot prove one caused the other, so present it as something to investigate.

**Seasonality:** March is the strongest month across FY2021-FY2024 (฿961M in total), April the weakest (฿545M).

**Inventory health (as of March 2025):** 5,539 items ever sold. 3,067 sold in the last 12 months. 2,410 had no sale for 12+ months, 778 were slow (6-11 months), 133 are discontinued or "to be advised" but still selling.
Back-check with the real FY2025 orders: of the 2,410 "no sales" items, 79% still did not sell in FY2025.

**New products are not in the numbers:** items with no list price (mostly brand-new products) are removed by the cleaning rules, in the history and in FY2025 alike. In the FY2025 file that is 1,466 order lines, about ฿108M.

---------------------------------------------------------------------------------------------------

## 4. How the dashboard works (the functions)

### One page, drill-down
The app is a single page. Click a card or a chart bar to go deeper. **← Overview** or **↑ Drill up** buttons go back. State is kept in the browser session.

### First run and the launcher
Double-click `Start_Dashboard.bat`: it finds a suitable Python (3.10-3.13), installs the packages once, creates a **Mitsubishi TNIC Dashboard** shortcut with the Mitsubishi icon, and starts the dashboard. If `final_dataset_main.csv` is not in `data/`, a welcome screen offers two ways to load data: download the file from Google Drive, or import the raw files.

### Import & Process Data (the notebooks, built in)
Drop the raw Customer, Item and Sale Order History files (separate files or one workbook). The dashboard finds out which table is which, then runs the three notebook stages and writes `final_dataset_main.csv`:
* **Stage 1 Cleaning:** strips column names, removes exact duplicate rows, joins customer and item details, removes rows with no usable list price.
* **Stage 2 Transformation:** removes zero quantities and builds 33 features (time, discount and value, customer history, product demand, inventory risk, order status group, outlier caps).
* **Stage 3 Encoding:** ordered tiers, frequency counts and yes/no columns for modelling.
A step-by-step report shows what each step did and how many rows it removed. A test runs the original notebook code and the ported code on the same input: the output is identical at every stage.
**Do not press "Process" with "Replace the current dataset" ticked during the demo** unless you are importing the full raw FY2021-FY2024 files: importing only the FY2025 workbook would replace the dataset with FY2025 alone.

### Main Panel (left sidebar), global filters
Date range, Industry, Product category, Customer type (All / VIP / Non-VIP), Order status. They change the Overview and the "More analysis" pages. **↺ Reset filters** puts everything back. The forecast pages ignore the filters (they are built on the full history).

### Executive Overview (home)
* 8 KPI cards: Total Revenue, Orders, Active Customers, Average Order Value, Units, Average Discount, VIP Revenue Share, Top-10 Customer Share. The badge compares with the previous period of equal length.
* **Business Questions** cards (hover lifts them): Sales Forecast, Inventory Management, Growth, Model Accuracy. Three more cards: What-If Scenarios, Add New Data, Import & Process Data.
* "More analysis" buttons: Products, Customers, Industries, Orders.
* **Which model powers what** table, then four charts (monthly revenue with 3-month average, share of revenue by category, top 8 industries (click a bar to open Industries), average discount by month).

### Q1 Sales Forecast
* Shows the FY2025 forecast made from FY2021-FY2024 only, with a low-high range.
* **Drill down:** Company total → click a category bar (or use the selector) → click an item bar (or use the item selector). Each level has its own chart, monthly table and CSV download. **↑ Drill up** goes back.
* Switch **"Compare with the real FY2025 results"** to overlay reality: real total, full-year error, monthly accuracy, and how many months fell inside the range.
* Item ranges mean the item's typical month-to-month swing (10th-90th percentile of its own last 24 months).

### Q2 Inventory Management (as of March 2025)
Tabs: **Priorities (ABC × XYZ)**: A/B/C by revenue share (80% / 95%), X/Y/Z by demand variability; click a bubble to open a segment. **Reorder planner**: set lead time and service level; safety stock = z × monthly std × √lead time; reorder point = demand during lead time + safety stock. **Slow & dead stock**: by months since last sale. **Stock on hand**: upload your stock (item, on_hand) to see cover, excess and shortage. **Back-check vs real FY2025**: how the plan held up.

### Q3 Product & Category Growth
Revenue by fiscal year, YoY and CAGR by category (FY2021-FY2024), the FY2025 forecast per category, click a bar to drill into a category, then top growing and declining items. A part-year is left out so growth is never distorted.

### Q4 Model Accuracy
Stage 1 validation, Stage 2 final test, accuracy at four levels (company × month, company × year, category × month, item × month), forecast vs real by category, **your team's four quantity models**, every candidate vs the real result, the model map, and models tested but not used (with reasons).

### What-If Scenarios
Baseline = the validated FY2025 forecast (or your updated forecast). Levers: demand change, list price, extra discount, price elasticity, top customers lost, new-item revenue, category scope. Presets are included. A waterfall shows what moves revenue. Scenarios can be saved and compared. A second tab stresses the inventory plan (lead time, service level, demand, variability).
**These are assumptions, not predictions.** The data has no costs, so there is no profit view.

### Add New Data
Upload CSV/Excel (required: date, item code, quantity, base price). The file passes the same cleaning rules (exact duplicates, items without a list price, quantity > 0) and a report shows what was accepted or removed. Accepted rows are saved in `data/added/` and flow into every page. **Retrain forecast on all data** forecasts the 12 months after the last complete month. Adding the FY2025 file gives an FY2026 forecast of about **฿2.00B** (+1.2% on FY2025).

### Model cards on every page
A dark banner lists each model or method on that page: what it is, what it does there, and its accuracy (or a back-check when there is nothing to score).

---------------------------------------------------------------------------------------------------

## 5. The models, and the results

| Part of the dashboard | Method | Why | Accuracy (validation FY2024 / final FY2025) |
|---|---|---|---|
| Company revenue by month | **Gradient Boosting** on the last 3 months and the calendar month | Highest validation accuracy among the company-level candidates | 90% / 87% monthly; full-year total −0.04% in FY2025 |
| Category and item split | **Sales-mix allocation**: company forecast × each item's recent sales share | Beat every machine-learning splitter on category revenue in validation | 79% / 80% (category × month) |
| ABC × XYZ, safety stock, dead stock | Rules and statistics (no machine learning) | Transparent and explainable | A-class kept 79% of real FY2025 revenue; reorder points covered real demand for 93% of items that sold; 79% of dead flags stayed dead |
| Category growth direction | Sales-mix outlook | (a check, not a selling point) | right for only 2 of 7 categories |

Best categories in the FY2025 test: PLC 84%, INV 84%, SV 82%, HMI 82% monthly accuracy. Small categories are weak: Robot 43%, Scada 51%.

**Your team's four quantity models (RandomForest, LightGBM, XGBoost, Hurdle)** were tested in the same leak-free way:

| Model | Item units, validation / final | Category revenue when used to split the company forecast, validation / final |
|---|---|---|
| RandomForest | 26% / 35% | 74% / 79% |
| Hurdle (two-stage) | 25% / 33% | 73% / 80% |
| LightGBM | not run in this build | not run |
| XGBoost | not run in this build | not run |
| Recent-sales mix (used) | 30% / 32% | 79% / 80% |

What to say: *"We tested all four. Random Forest and Hurdle ran. In validation they did not beat the simple sales-mix method at category level, and for item units they were worse in validation (26% and 25% vs 30%) and slightly better in the final test (35% and 33% vs 32%), so there is no consistent edge. The dashboard uses the simple method by default. LightGBM and XGBoost are built in (Tweedie objective) but need the libraries installed; one setting in `config.py` (`ITEM_MIX_MODEL`) switches the dashboard to any of the four."*

**Why the shared project's reported accuracy may look higher:** from reading its code, its test fed real previous months into each month's prediction, which a true 12-month forecast does not have. Our test forecasts 12 months ahead using only earlier data. (We did not run the shared project's own code.)

**A correction worth mentioning:** an earlier version compared the forecast with the raw FY2025 file (฿2,215M). The raw file still had duplicates, unpriced new products and un-grouped statuses, which the history had already been cleaned of. Cleaned the same way, the real FY2025 is ฿1,981M. The steps: −฿37M duplicate rows, −฿108M orders for items with no list price, −฿89M from the status grouping (pending fulfilment and partly fulfilled count as Loss).

---------------------------------------------------------------------------------------------------

## 6. Honest limits (say these before you are asked)

1. The full-year total was almost exact, but some of that is luck. The monthly shape was 87% accurate, and small categories are weak (Robot 43%, Scada 51%).
2. Category growth direction is not reliable: the forecast got it right for only 2 of 7 categories. Use the forecast for totals, not to rank categories by growth.
3. Item-by-month forecasts are weak (about 15-35% accurate) because most items sell rarely and in lumps. Use them for ranking and safety stock.
4. Ranges are close but not perfect: the real value fell inside the range in 11 of 12 months at company level, about 77% of category-months and 78% of top-item months (target about 80%).
5. No stock levels or supplier lead times in the data: safety stock uses assumptions you set.
6. No product launch dates, so "older than 5 years" cannot be measured; months since last sale is the proxy.
7. Brand-new products without a list price are excluded by the cleaning rules, so their sales are not in these numbers.
8. The shared project's VIP 37% discount and partial-order price cut are **not** applied (not in our dataset's `Total Sales Amount`).
9. LightGBM and XGBoost could not be run in the build environment.
10. FY2023 (−32.9%) is a shock no model predicted; we show it but do not use it to rank models.

---------------------------------------------------------------------------------------------------

## 7. Suggested 7-minute demo

1. **Overview (1 min):** KPIs, point at the cards, show the Reset button and one filter (Category = PLC), then reset.
2. **Sales Forecast (2 min):** company chart with range → switch on "Compare with real FY2025" → click the PLC bar → click an item bar → show the item range → drill up.
3. **Inventory (1.5 min):** click the A-Z bubble → Reorder planner (change lead time) → Slow & dead stock.
4. **Growth (30 s):** click a category bar.
5. **Model Accuracy (1 min):** stages strip, model bars, team's four models.
6. **What-If (1 min):** preset "Lose the top 3 customers" → waterfall.
7. **Import (30 s, show only):** open Import & Process Data, show the three stages and the report from a previous run. Do not process live.

---------------------------------------------------------------------------------------------------

## 8. Likely questions

**Why Gradient Boosting for the company total?** Best validation accuracy of the candidates for company monthly revenue, and it handles seasonality with few inputs.

**Why not LightGBM / XGBoost / Random Forest?** We tested Random Forest and Hurdle: no consistent edge over the simple sales mix. LightGBM and XGBoost are supported, not scored here. Switch with `ITEM_MIX_MODEL`.

**Why exclude Loss orders?** They never shipped or were billed, so they are not real demand. Change `FORECAST_EXCLUDE_STATUS` in `config.py` to include them.

**How is accuracy measured?** Accuracy = 1 − WAPE. WAPE = sum of absolute errors ÷ sum of actual.

**What is the difference between validation and the final test?** Validation (FY2023, FY2024) is where we pick models, using history only. The final test (FY2025) is run once against the real result.

**Why is the FY2025 total so accurate but categories less?** Errors in different categories partly cancel in the total. Monthly accuracy (87%) and small-category accuracy are the fairer measures.

**Why is FY2023 accuracy low?** Revenue fell 32.9% and no model predicted it. We show it but do not use it to rank models.

**What does the range mean?** The real value should land between low and high about 8 months in 10.

**Can it forecast new products?** No. They also have no list price yet, so the cleaning rules leave them out.

**What happens when I import raw files?** The dashboard runs the three notebook stages (clean, transform, encode), writes `final_dataset_main.csv`, and shows a report. A test proves the output is identical to the notebooks.

**Why does the dataset not come with the GitHub project?** The file is about 140 MB, over GitHub's 100 MB limit, so it is on Google Drive. The dashboard shows a welcome screen with the link, or you can import the raw files instead.

**What is ABC × XYZ?** A/B/C = how much revenue an item makes. X/Y/Z = how steady its demand is. AZ = valuable but erratic, the watch list.

**Is What-If a prediction?** No. It is your assumptions applied to the baseline. Price elasticity is an input (default −1.0), not measured.

**How do we add FY2026 data?** Add New Data → upload → check report → Add → Retrain forecast.
