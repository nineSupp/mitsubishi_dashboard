"""Shared guard for views that need the saved forecast files."""
import streamlit as st
from ui.components import note


def require_outputs(ctx):
    if ctx.outputs is None:
        note("Forecast files not found. Run <code>python -m scripts.train_forecasts</code> once "
             "(and <code>python -m scripts.evaluate_models --fold FY2025</code> for the accuracy tables), then reload.", warn=True)
        return False
    return True
