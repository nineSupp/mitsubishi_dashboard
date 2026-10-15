"""Company/category-level monthly series models (ported from main_dashboard.py's forecast engine,
plus a growth-adjusted seasonal naive and an optional SARIMA when statsmodels is installed)."""
import warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:                                   # optional: friend's SARIMA approach
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    HAS_STATSMODELS = True
except ImportError:                    # pragma: no cover
    HAS_STATSMODELS = False


def _features(hist, month_num, t, use_trend):
    h = np.asarray(hist, dtype=float)
    f = [h[-1], h[-2], h[-3], h[-3:].mean(), np.sin(2 * np.pi * month_num / 12), np.cos(2 * np.pi * month_num / 12)]
    if use_trend:
        f.append(t)
    return f


def forecast_log(y, months, horizon, key):
    """Forecast `horizon` months in log1p space. y: array, months: DatetimeIndex of y."""
    n = len(y)
    if key == 'naive':
        return np.array([y[n - 12 + (h % 12)] for h in range(horizon)])
    if key == 'drift_naive':           # last year's months scaled by the latest year-on-year growth in levels
        last, prev = np.expm1(y[-12:]).sum(), np.expm1(y[-24:-12]).sum() if n >= 24 else np.nan
        g = np.clip(last / prev, 0.7, 1.3) if prev and not np.isnan(prev) else 1.0
        return np.log1p(np.expm1(y[n - 12:n]) * g)
    use_trend = key == 'ridge'
    X = np.array([_features(y[:i], months[i].month, i, use_trend) for i in range(3, n)])
    model = (GradientBoostingRegressor(n_estimators=150, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=42)
             if key == 'gbm' else make_pipeline(StandardScaler(), Ridge(alpha=3.0)))
    model.fit(X, y[3:])
    hist, out = list(y), []
    for h in range(horizon):
        month_num = (months[-1] + pd.DateOffset(months=h + 1)).month
        pred = float(model.predict(np.array([_features(hist, month_num, n + h, use_trend)]))[0])
        out.append(pred); hist.append(pred)
    return np.array(out)


def sarima_forecast(y, horizon):
    """Friend's SARIMA (log space, AIC-selected). Only runs when statsmodels is available."""
    best = (np.inf, None)
    for order, seas in [((1, 1, 1), (1, 1, 1, 12)), ((1, 1, 0), (1, 1, 0, 12)), ((0, 1, 1), (0, 1, 1, 12)),
                        ((1, 1, 1), (0, 1, 1, 12)), ((0, 1, 0), (1, 1, 0, 12))]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                res = SARIMAX(y, order=order, seasonal_order=seas, enforce_stationarity=False,
                              enforce_invertibility=False).fit(disp=False)
            if res.aic < best[0]:
                best = (res.aic, res)
        except Exception:
            continue
    return best[1].get_forecast(steps=horizon).predicted_mean if best[1] is not None else np.full(horizon, np.nan)


SERIES_MODELS = {
    'Ridge (trend + seasonality) [dashboard v1]': 'ridge',
    'Gradient Boosting (lags + seasonality) [dashboard v1]': 'gbm',
    'Seasonal naive [dashboard v1]': 'naive',
    'Seasonal naive x latest growth': 'drift_naive',
}
if HAS_STATSMODELS:
    SERIES_MODELS['SARIMA (log) [friend]'] = 'sarima'


def predict_series(values, months, horizon, key):
    """values: monthly series (levels), months: DatetimeIndex. Returns levels for the next `horizon` months."""
    y = np.log1p(np.clip(np.asarray(values, float), 0, None))
    if key == 'sarima':
        return np.clip(np.expm1(np.asarray(sarima_forecast(y, horizon))), 0, None)
    return np.clip(np.expm1(forecast_log(y, months, horizon, key)), 0, None)


HOLDOUT = 6   # months held out to calibrate the forecast range


def forecast_with_range(values, months, horizon=12, key='gbm'):
    """Point forecast + ~80% range. The range comes from how wrong the model was on its own last
    `HOLDOUT` training months (same approach as the original dashboard)."""
    s = np.asarray(values, float)
    y = np.log1p(np.clip(s, 0, None))
    fc = np.clip(np.expm1(forecast_log(y, months, horizon, key)), 0, None)
    back = np.clip(np.expm1(forecast_log(y[:-HOLDOUT], months[:-HOLDOUT], HOLDOUT, key)), 0, None)
    sigma = max(float(np.sqrt(np.mean((np.log1p(back) - y[-HOLDOUT:]) ** 2))), 0.05)
    widen = np.sqrt(np.arange(1, horizon + 1) / 3.5)
    return fc, fc * np.exp(-1.28 * sigma * widen), fc * np.exp(1.28 * sigma * widen)
