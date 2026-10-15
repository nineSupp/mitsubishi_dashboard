"""Forecast accuracy metrics. Accuracy = 1 - WAPE (never below 0)."""
import numpy as np


def wape(actual, pred):
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    den = np.abs(actual).sum()
    return float(np.abs(actual - pred).sum() / den) if den > 0 else np.nan


def accuracy(actual, pred):
    w = wape(actual, pred)
    return float(max(1 - w, 0)) if not np.isnan(w) else np.nan


def bias(actual, pred):
    """Positive = over-forecast, negative = under-forecast (as a share of actual)."""
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    den = actual.sum()
    return float((pred.sum() - den) / den) if den > 0 else np.nan


def mae(actual, pred):
    return float(np.mean(np.abs(np.asarray(actual, float) - np.asarray(pred, float))))


def summarise(actual, pred):
    return dict(WAPE=wape(actual, pred), Accuracy=accuracy(actual, pred), Bias=bias(actual, pred), MAE=mae(actual, pred))
