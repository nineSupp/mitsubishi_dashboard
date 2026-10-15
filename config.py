"""Central configuration: paths, brand palette and forecasting constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"          # put final_dataset_main.csv and TNIC_Data_2025.xlsx here
PROCESSED_DIR = DATA_DIR / "processed"   # master tables + processing report written by the import pipeline
OUTPUT_DIR = ROOT / "outputs"     # written by scripts/train_forecasts.py, read by the dashboard
ASSETS_DIR = ROOT / "assets"

HISTORY_CSV = "final_dataset_main.csv"      # names shown in messages; the lookup below also accepts variants
ACTUALS_XLSX = "TNIC_Data_2025.xlsx"

_PATTERNS = {
    "history": ["final_dataset_main.csv", "final_dataset_main*.csv"],
    "actuals": ["TNIC_Data_2025.xlsx", "TNIC*Data*2025*.xlsx", "*Data*2025*.xlsx"],
}


def find_data_file(kind, data_dir=None):
    """Locate the history CSV or the FY2025 workbook, tolerating names like 'TNIC Data_2025.xlsx' or '..._1.csv'."""
    folder = Path(data_dir) if data_dir else DATA_DIR
    for pat in _PATTERNS[kind]:
        hits = sorted(p for p in folder.glob(pat) if not p.name.startswith("~$"))
        if hits:
            return hits[0]
    return None

# Branding (copied from main_dashboard.py)
LOGO_FILE = ASSETS_DIR / "img" / "mitsu_logo2.png"
ICON_FILE = ASSETS_DIR / "img" / "mitsu_icon_logo.png"
BRAND_SEQ = ['#E60012', '#005BAC', '#333333', '#8C8C8C', '#F26B76', '#5B9BD5', '#B3001B', '#DBDBDB']
RED, BLUE, CHARCOAL = '#E60012', '#005BAC', '#333333'
CURRENCY = "฿"          # Thai Baht, shown on every money value
WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

TEAM_MEMBERS = [
    ("1. Suppatouch Srinual", "2420210037"),
    ("2. Paing Myo Han Kyaw", "2420210284"),
    ("3. Hideki Miyauchi", "2420210011"),
    ("4. Chayuth Eabsakul", "2420110336"),
    ("5. Hiroyasu Ishida", "2420110161")
]

# Forecasting
# "Loss" = Closed orders: never shipped or billed, so they are not realised demand.
FORECAST_EXCLUDE_STATUS = ["Loss"]
ORIGIN_FY = 2024          # last fiscal year used for training the backtest model (FY2024 = Apr-2024..Mar-2025)
ACTUAL_FY = 2025          # fiscal year with real actuals (Apr-2025..Mar-2026)

# Which model splits the company forecast across categories and items:
#   'flat' (default, recent sales mix) | 'random_forest' | 'lightgbm' | 'xgboost' | 'hurdle'
# The company total always comes from Gradient Boosting; the chosen model only decides the mix.
# LightGBM / XGBoost need `pip install lightgbm xgboost`; if missing, the dashboard falls back to 'flat'.
ITEM_MIX_MODEL = "flat"

# Where to download the processed dataset (too big for GitHub). Shown on the setup screen and in the README.
DATA_DOWNLOAD_URL = "https://drive.google.com/drive/folders/1ALNk8cdzmvdQcQVyC5cI3fX7Y3MUmTv1?usp=sharing"
