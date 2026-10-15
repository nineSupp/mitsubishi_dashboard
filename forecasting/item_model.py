"""Item-level monthly demand model (recursive multi-step) + simple baselines.

The same `make_features` function builds the training rows AND the features used while
forecasting recursively, so there is no train/serve mismatch. Every feature at month t only
uses information from months < t (no look-ahead).
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import (HistGradientBoostingClassifier, HistGradientBoostingRegressor,
                              RandomForestClassifier, RandomForestRegressor)

FEATURES = ['lag1', 'lag2', 'lag3', 'lag12', 'roll3', 'roll6', 'roll12', 'std3', 'since_last', 'active12',
            'activity_rate', 'age', 'sin_m', 'cos_m', 'fy_end', 'cat_season', 'log_price', 'cat_code', 'prod_code']
PROD_CODES = {'Continue': 0, 'Discontinue': 1, 'To Be Advised': 2}
MIN_HISTORY = 12     # first column that has a full 12-month look-back


class Context:
    """Static look-ups derived from the training history only."""

    def __init__(self, panel, n_train):
        self.items = panel.items
        self.n_train = n_train
        cats = sorted(panel.meta['category'].unique())
        self.cat_map = {c: i for i, c in enumerate(cats)}
        self.cat_code = panel.meta['category'].map(self.cat_map).to_numpy(float)
        self.prod_code = panel.meta['production'].map(PROD_CODES).fillna(0).to_numpy(float)
        self.first_sale = panel.meta['first_sale'].to_numpy()
        self.months = panel.months
        # category x month quantity totals for the seasonal index
        self.cat_idx = self.cat_code.astype(int)
        self.n_cat = len(cats)
        tot = np.zeros((self.n_cat, panel.Q.shape[1]))
        np.add.at(tot, self.cat_idx, panel.Q)
        self.cat_tot = tot
        self.fy_of_col = np.array([(m.year if m.month >= 4 else m.year - 1) for m in panel.months])

    def season_index(self, t, cal_month, fy_t):
        """Average share of the fiscal year's category quantity that fell in `cal_month`, using ONLY
        fiscal years that finished before column t."""
        shares = []
        for fy in np.unique(self.fy_of_col):
            if fy >= fy_t:
                continue
            cols = np.where(self.fy_of_col == fy)[0]
            cols = cols[cols < min(t, self.n_train)]
            if len(cols) < 12:
                continue
            yr = self.cat_tot[:, cols].sum(1)
            mc = [c for c in cols if self.months[c].month == cal_month]
            if not mc:
                continue
            shares.append(np.where(yr > 0, self.cat_tot[:, mc[0]] / np.where(yr > 0, yr, 1), 1 / 12))
        return np.mean(shares, 0) if shares else np.full(self.n_cat, 1 / 12)


def _month_info(ctx, t, month_ts=None):
    ts = month_ts if month_ts is not None else ctx.months[t]
    cal = ts.month
    fy = ts.year if cal >= 4 else ts.year - 1
    return cal, fy


def make_features(M, Rv, t, ctx, month_ts=None, t_hist=None):
    """Feature matrix [items x len(FEATURES)] to predict column t.
    History windows use M[:, :t_hist] (default t_hist = t); calendar features describe the target month."""
    th = t if t_hist is None else t_hist
    n = M.shape[0]
    h = M[:, :th]
    w3, w6, w12 = M[:, th - 3:th], M[:, th - 6:th], M[:, th - 12:th]
    sold = h > 0.5
    rev_sold = sold[:, ::-1]
    any_sale = rev_sold.any(1)
    since_last = np.minimum(np.where(any_sale, rev_sold.argmax(1), th).astype(float), 36)
    first_idx = np.where(any_sale, sold.argmax(1), -1)
    age = np.where(first_idx >= 0, np.minimum(th - first_idx, 36), 0).astype(float)
    active_len = np.maximum(th - np.where(first_idx >= 0, first_idx, th), 1)
    activity_rate = np.where(first_idx >= 0, sold.sum(1) / active_len, 0.0)
    q12, r12 = w12.sum(1), Rv[:, th - 12:th].sum(1)
    log_price = np.log1p(np.where(q12 > 0, r12 / np.where(q12 > 0, q12, 1), 0))
    cal, fy = _month_info(ctx, t, month_ts)
    season = ctx.season_index(th, cal, fy)[ctx.cat_idx]
    X = np.column_stack([
        M[:, th - 1], M[:, th - 2], M[:, th - 3], M[:, th - 12],
        w3.mean(1), w6.mean(1), w12.mean(1), w3.std(1), since_last, (w12 > 0.5).sum(1),
        activity_rate, age,
        np.full(n, np.sin(2 * np.pi * cal / 12)), np.full(n, np.cos(2 * np.pi * cal / 12)),
        np.full(n, float(cal == 3)), season, log_price, ctx.cat_code, ctx.prod_code])
    return X, any_sale


def training_set(panel, ctx, n_train):
    """Rows for every month t in [12, n_train) and every item that had sold before t."""
    Xs, ys = [], []
    for t in range(MIN_HISTORY, n_train):
        X, ever = make_features(panel.Q, panel.R, t, ctx)
        Xs.append(X[ever])
        ys.append(panel.Q[ever, t])
    return np.vstack(Xs), np.concatenate(ys)


def available_kinds():
    """Model kinds that can run in this environment (LightGBM / XGBoost are optional installs)."""
    kinds = {'rf', 'hgb', 'hgb_poisson', 'hurdle'}
    for kind, module in (('lgbm', 'lightgbm'), ('xgb', 'xgboost')):
        try:
            __import__(module)
            kinds.add(kind)
        except ImportError:
            pass
    return kinds


class ItemDemandModel:
    """kind: 'rf' | 'hgb' | 'hgb_poisson' | 'hurdle' | 'lgbm' | 'xgb'.
    rf / hgb / hurdle learn log1p(quantity); hgb_poisson / lgbm / xgb learn raw counts (Poisson / Tweedie loss)."""

    def __init__(self, kind='hgb', n_estimators=150, seed=42):
        self.kind, self.n_estimators, self.seed = kind, n_estimators, seed

    def _reg(self):
        if self.kind in ('hgb', 'hgb_poisson'):
            return HistGradientBoostingRegressor(loss='poisson' if self.kind == 'hgb_poisson' else 'squared_error',
                                                 max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                                 min_samples_leaf=40, l2_regularization=1.0, random_state=self.seed)
        return RandomForestRegressor(n_estimators=self.n_estimators, max_depth=12, min_samples_leaf=5,
                                     n_jobs=-1, random_state=self.seed)

    def fit(self, X, y):
        if self.kind == 'hurdle':
            self.clf = RandomForestClassifier(n_estimators=self.n_estimators, max_depth=12, min_samples_leaf=5,
                                              n_jobs=-1, random_state=self.seed).fit(X, (y > 0).astype(int))
            pos = y > 0
            self.reg = RandomForestRegressor(n_estimators=self.n_estimators, max_depth=12, min_samples_leaf=5,
                                             n_jobs=-1, random_state=self.seed).fit(X[pos], np.log1p(y[pos]))
        elif self.kind == 'hgb_poisson':            # raw counts: predicts the mean (unbiased totals)
            self.reg = self._reg().fit(X, y)
        elif self.kind == 'lgbm':                   # LightGBM, Tweedie objective suits zero-heavy demand
            import lightgbm as lgb
            self.reg = lgb.LGBMRegressor(objective='tweedie', tweedie_variance_power=1.3, n_estimators=400,
                                         learning_rate=0.05, num_leaves=31, min_child_samples=40, subsample=0.8,
                                         subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                                         random_state=self.seed, n_jobs=-1, verbose=-1).fit(X, y)
        elif self.kind == 'xgb':                    # XGBoost with regularisation, Tweedie objective
            import xgboost as xgb
            self.reg = xgb.XGBRegressor(objective='reg:tweedie', tweedie_variance_power=1.3, n_estimators=400,
                                        learning_rate=0.05, max_depth=6, subsample=0.8, colsample_bytree=0.8,
                                        reg_lambda=1.0, random_state=self.seed, n_jobs=-1, tree_method='hist').fit(X, y)
        else:
            self.reg = self._reg().fit(X, np.log1p(y))
        return self

    def predict(self, X):
        if self.kind == 'hurdle':
            return np.clip(self.clf.predict_proba(X)[:, 1] * np.expm1(self.reg.predict(X)), 0, None)
        if self.kind in ('hgb_poisson', 'lgbm', 'xgb'):
            return np.clip(self.reg.predict(X), 0, None)
        return np.clip(np.expm1(self.reg.predict(X)), 0, None)


def recursive_forecast(model, panel, ctx, n_train, horizon=12):
    """Forecast `horizon` months after column n_train-1 using only data in columns < n_train."""
    T = n_train + horizon
    M = np.zeros((panel.Q.shape[0], T)); M[:, :n_train] = panel.Q[:, :n_train]
    Rv = np.zeros_like(M); Rv[:, :n_train] = panel.R[:, :n_train]
    # extend the context month list so season/calendar logic works for future columns
    fut = pd.date_range(panel.months[n_train - 1] + pd.DateOffset(months=1), periods=horizon, freq='MS')
    price = _last_price(panel, n_train)
    out = np.zeros((M.shape[0], horizon))
    for k in range(horizon):
        t = n_train + k
        X, ever = make_features(M, Rv, t, ctx, month_ts=fut[k])
        p = model.predict(X)
        p = np.where(ever, p, 0.0)          # items that never sold cannot be forecast (cold start)
        M[:, t] = p
        Rv[:, t] = p * price
        out[:, k] = p
    return out, fut


def _last_price(panel, n_train, window=12):
    q = panel.Q[:, n_train - window:n_train].sum(1)
    r = panel.R[:, n_train - window:n_train].sum(1)
    p = np.where(q > 0, r / np.where(q > 0, q, 1), np.nan)
    # fall back to the item's all-time average price, then to the category average
    qa, ra = panel.Q[:, :n_train].sum(1), panel.R[:, :n_train].sum(1)
    pa = np.where(qa > 0, ra / np.where(qa > 0, qa, 1), np.nan)
    p = np.where(np.isnan(p), pa, p)
    cat = panel.meta['category'].to_numpy()
    cat_avg = pd.Series(p).groupby(cat).transform('mean').to_numpy()
    p = np.where(np.isnan(p), cat_avg, p)
    return np.nan_to_num(p, nan=np.nanmean(p))


# ---------------------------- baselines (no learning) ----------------------------
def baseline_forecasts(panel, ctx, n_train, horizon=12):
    """Return {name: [items x horizon]} for simple, transparent benchmark methods."""
    Q = panel.Q
    flat = np.repeat(Q[:, n_train - 12:n_train].mean(1, keepdims=True), horizon, axis=1)
    naive = Q[:, n_train - 12:n_train].copy()
    fut = pd.date_range(panel.months[n_train - 1] + pd.DateOffset(months=1), periods=horizon, freq='MS')
    seas = np.zeros_like(flat)
    for k, ts in enumerate(fut):
        idx = ctx.season_index(n_train + k, ts.month, ts.year if ts.month >= 4 else ts.year - 1)[ctx.cat_idx]
        seas[:, k] = flat[:, k] * np.clip(idx * 12, 0.3, 3.0)
    return {'Flat 12-month average': flat, 'Seasonal naive (same month last year)': naive,
            'Seasonal average (12m avg x category seasonality)': seas}


# ------------------------- direct multi-horizon (no recursion) -------------------------
def direct_training_set(panel, ctx, n_train, horizon=12, origin_step=2):
    """Rows (item, origin, h): features use history up to the origin only, target is the month h ahead."""
    Xs, ys = [], []
    for th in range(MIN_HISTORY, n_train, origin_step):
        for h in range(1, horizon + 1):
            t = th + h - 1
            if t >= n_train:
                break
            X, ever = make_features(panel.Q, panel.R, t, ctx, t_hist=th)
            Xs.append(np.column_stack([X[ever], np.full(ever.sum(), h)]))
            ys.append(panel.Q[ever, t])
    return np.vstack(Xs), np.concatenate(ys)


def direct_forecast(model, panel, ctx, n_train, horizon=12):
    fut = pd.date_range(panel.months[n_train - 1] + pd.DateOffset(months=1), periods=horizon, freq='MS')
    out = np.zeros((panel.Q.shape[0], horizon))
    for k in range(horizon):
        X, ever = make_features(panel.Q, panel.R, n_train + k, ctx, month_ts=fut[k], t_hist=n_train)
        p = model.predict(np.column_stack([X, np.full(len(X), k + 1)]))
        out[:, k] = np.where(ever, p, 0.0)
    return out, fut
