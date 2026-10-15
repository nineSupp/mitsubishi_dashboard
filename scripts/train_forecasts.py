"""Build every forecast artefact the dashboard reads (writes to outputs/).

    python -m scripts.train_forecasts

Protocol (FY = April to March):
  Stage 1  validation : train FY2021-22 -> test FY2023, train FY2021-23 -> test FY2024   (scripts/evaluate_models.py)
  Stage 2  final test : train FY2021-FY2024 only -> forecast FY2025 -> compare with the real FY2025 orders
                        in TNIC_Data_2025.xlsx. The real FY2025 numbers are never used for training.
"""
import json
from datetime import date
import pandas as pd

import config
from core.data import build_dataset
from core.watchdog import busy
from forecasting.panel import build_panel, truncate
from forecasting.pipeline import official_forecast, inventory_profile, COMPANY_MODEL_KEY
from forecasting.series_models import SERIES_MODELS, predict_series


def main():
    with busy():
        _main()


def _main():
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    df, _, _ = build_dataset(include_actuals=True)      # FY2025 actuals are loaded only to score the forecast
    full = build_panel(df)
    n_back = len(full.months) - 12                       # 48 months = FY2021..FY2024
    train_panel = truncate(full, n_back)

    fc = official_forecast(full, n_back)                 # uses columns < 48 only; actuals attached for comparison
    fc['company'].to_csv(config.OUTPUT_DIR / 'forecast_company.csv', index=False)
    fc['category'].to_csv(config.OUTPUT_DIR / 'forecast_category.csv', index=False)
    fc['item'].to_csv(config.OUTPUT_DIR / 'forecast_item.csv', index=False, float_format='%.3f')

    # every candidate model's FY2025 company revenue forecast (for the comparison chart)
    series, months = full.R.sum(0), full.months
    cols = {label: predict_series(series[:n_back], months[:n_back], 12, key) for label, key in SERIES_MODELS.items()}
    cmp_df = pd.DataFrame(cols); cmp_df.insert(0, 'month', months[n_back:]); cmp_df['actual'] = series[n_back:]
    cmp_df.to_csv(config.OUTPUT_DIR / 'fy25_company_by_model.csv', index=False)

    # inventory profile as of Mar 2025; FY2025 actual units/revenue are attached for the back-check only
    prof = inventory_profile(train_panel, fc['item'])
    idx = {it: i for i, it in enumerate(full.items)}
    pos = prof['item'].map(idx).to_numpy()
    prof['actual_fy25_qty'] = full.Q[pos, n_back:].sum(1)
    prof['actual_fy25_revenue'] = full.R[pos, n_back:].sum(1)
    prof.to_csv(config.OUTPUT_DIR / 'inventory_profile.csv', index=False, float_format='%.4f')

    ev = config.OUTPUT_DIR / 'eval_all_folds.csv'
    info = dict(generated=str(date.today()), company_model=COMPANY_MODEL_KEY, trained_on='FY2021-FY2024 (Apr 2021 - Mar 2025)',
                forecast_year='FY2025 (Apr 2025 - Mar 2026)', compared_with='TNIC_Data_2025.xlsx (real FY2025 orders)',
                outlier_cap_units=fc['cap'], revenue_definition='Base price x quantity, Closed ("Loss") orders excluded',
                evaluation_file=ev.name if ev.exists() else 'run scripts.evaluate_models first')
    (config.OUTPUT_DIR / 'run_info.json').write_text(json.dumps(info, indent=2))

    c = fc['company']
    print('FY2025 forecast', round(c['forecast'].sum() / 1e6, 1), 'M | real FY2025', round(c['actual'].sum() / 1e6, 1), 'M')
    print('inventory rows', len(prof), prof['flag'].value_counts().to_dict())


if __name__ == '__main__':
    main()
