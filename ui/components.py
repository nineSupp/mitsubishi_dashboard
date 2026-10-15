"""Small reusable UI helpers (formatting, KPI cards, chart styling, drill-down navigation widgets)."""
import re

import numpy as np
import pandas as pd
import streamlit as st

import config

VIEW_TITLES = {
    'forecast': 'Sales Forecast', 'inventory': 'Inventory Management', 'growth': 'Product & Category Growth',
    'accuracy': 'Model Accuracy', 'whatif': 'What-If Scenarios', 'upload': 'Add New Data', 'import': 'Import & Process Data', 'products': 'Product Performance', 'customers': 'Customers',
    'industries': 'Industries', 'orders': 'Orders',
}


# ---------- formatting ----------
def fmt_num(x, prefix=""):
    if x is None or pd.isna(x):
        return "–"
    sign, x = ("-", abs(x)) if x < 0 else ("", x)
    a = abs(x)
    if a >= 1e9:
        s = f"{x / 1e9:,.2f}B"
    elif a >= 1e6:
        s = f"{x / 1e6:,.2f}M"
    elif a >= 1e3:
        s = f"{x / 1e3:,.1f}K"
    else:
        s = f"{x:,.0f}"
    return f"{sign}{prefix}{s}"


def fmt_money(x):
    return fmt_num(x, config.CURRENCY)


def fmt_pct(x, digits=1):
    return "–" if x is None or pd.isna(x) else f"{x * 100:.{digits}f}%"


def pct_change(cur, prev):
    return (cur - prev) / prev if prev not in (0, None) and not pd.isna(prev) else np.nan


def delta_badge(delta, fallback, note="vs prev. period", inverse=False):
    """Return (text, tone) for a KPI badge. `fallback` is shown when there is no previous period."""
    if delta is None or pd.isna(delta):
        return fallback, "neutral"
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "↔")
    good = (delta <= 0) if inverse else (delta >= 0)
    tone = "neutral" if abs(delta) < 1e-9 else ("positive" if good else "negative")
    return f"{arrow} {delta * 100:+.1f}% {note}", tone


# ---------- widgets ----------
def kpi_card(title, value, badge_text="", tone="neutral"):
    badge = f'<span class="metric-badge badge-{tone}">{badge_text}</span>' if badge_text else ""
    st.markdown(
        f'<div class="metric-card"><div class="metric-title">{title}</div>'
        f'<div class="metric-value">{value}</div>{badge}</div>', unsafe_allow_html=True)


GREY = '#6C757D'            # theme grey: chart text on the (always light) chart cards
CUR = config.CURRENCY


def _money_axis(fig, axis):
    """Axis shows money: baht prefix, k / M / B suffixes, full number on hover."""
    upd = fig.update_xaxes if axis == 'x' else fig.update_yaxes
    upd(tickprefix=CUR, tickformat='', exponentformat='B', hoverformat=',.0f')


def style_fig(fig, height=340, legend=True, x_title=None, y_title=None, money=None, legend_pos='top'):
    """One chart style everywhere: grey text, light grid, legend that always stays inside the card,
    axis titles so the reader knows what each axis shows."""
    top = 52 if (legend and legend_pos == 'top') else 24
    right = 130 if (legend and legend_pos == 'right') else 24
    if legend_pos == 'right':
        leg = dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02)
    else:
        leg = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    leg.update(font=dict(color=GREY, size=12), title=dict(text=''))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color=GREY), margin=dict(l=16, r=right, t=top, b=16),
        height=height, showlegend=legend, legend=leg)
    fig.update_xaxes(showgrid=False, tickfont=dict(color=GREY), title_font=dict(color=GREY, size=12),
                     linecolor='#DDE1E6', automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor='#EAEAEA', tickfont=dict(color=GREY), title_font=dict(color=GREY, size=12),
                     zerolinecolor='#DDE1E6', automargin=True)
    if money in ('x', 'y'):
        _money_axis(fig, money)
    if x_title is not None:
        fig.update_xaxes(title_text=x_title)
    if y_title is not None:
        fig.update_yaxes(title_text=y_title)
    return fig


def _card():
    """Container that draws the chart card (border, padding). The card grows with its content, so nothing is clipped."""
    n = st.session_state.get('_chart_n', 0) + 1
    st.session_state['_chart_n'] = n
    try:
        return st.container(key=f"chartcard_{n}")
    except TypeError:                       # older Streamlit without container keys
        return st.container()


def show_chart(fig, height=340, legend=True, x_title=None, y_title=None, money=None, legend_pos='top'):
    style_fig(fig, height, legend, x_title, y_title, money, legend_pos)
    with _card():
        st.plotly_chart(fig, use_container_width=True)


def drill_chart(fig, key, on_pick, height=340, legend=True, x_title=None, y_title=None, money=None, legend_pos='top'):
    """A chart you can click. `on_pick(points, fig)` runs BEFORE the page reruns, so it may change widget values
    (for example the category selector) and views. Each pick starts a fresh chart so no bar stays highlighted."""
    epoch = st.session_state.setdefault('_epochs', {})
    full_key = f"{key}_{epoch.get(key, 0)}"
    style_fig(fig, height, legend, x_title, y_title, money, legend_pos)

    def _handle():
        sel = st.session_state.get(full_key)
        try:
            pts = list(sel['selection']['points'])
        except Exception:
            pts = []
        if pts:
            epoch[key] = epoch.get(key, 0) + 1
            on_pick(pts, fig)

    with _card():
        st.plotly_chart(fig, use_container_width=True, key=full_key, on_select=_handle, selection_mode="points")
        st.caption("Click a bar or point to drill down.")


# Columns that hold money get "(฿)" added to their header, in tables and CSV downloads.
MONEY_COLUMNS = {
    'Revenue', 'Revenue 12m', 'Forecast', 'Low (~80%)', 'High (~80%)', 'Real', 'Baseline', 'Scenario', 'baseline', 'scenario',
    'Forecast revenue', 'Real revenue', 'Real FY2025 revenue', 'Gross value', 'Discount', 'Avg order value', 'Avg price',
    'Avg unit price', 'Extra safety value', 'Excess value', 'Order value', 'Stock value', 'Actual', 'Low', 'High',
    'Forecast low', 'Forecast high', 'Change',
}


def label_money(df):
    """Return df with (฿) appended to money column headers (names in MONEY_COLUMNS or FY2021 / FY2025 forecast style)."""
    if not CUR:
        return df
    cols = {c: f"{c} ({CUR})" for c in df.columns
            if str(c) in MONEY_COLUMNS or re.fullmatch(r'FY\d{4}( forecast)?', str(c))}
    return df.rename(columns=cols) if cols else df


def show_table(df, **kwargs):
    st.dataframe(label_money(df), use_container_width=True, hide_index=True, **kwargs)


def csv_button(df, label, file_name, raw=False):
    """raw=True keeps the column names unchanged (for templates that must match an import format)."""
    out = df if raw else label_money(df)
    st.download_button(label, out.to_csv(index=False).encode("utf-8-sig"), file_name, "text/csv")


def note(text, warn=False):
    st.markdown(f'<div class="note-box{" warn" if warn else ""}">{text}</div>', unsafe_allow_html=True)


# ---------- drill-down navigation (single page: the "view" lives in session_state) ----------
def go(view):
    st.session_state['view'] = view


def current_view():
    return st.session_state.get('view', 'home')


def back_bar(view):
    left, right = st.columns([1, 6])
    with left:
        st.button("← Overview", key="back_home", on_click=go, args=('home',), use_container_width=True)
    with right:
        st.markdown(f'<div class="crumb">Overview &nbsp;›&nbsp; <b>{VIEW_TITLES.get(view, view)}</b></div>',
                    unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)


def drill_card(question, title, stat, sub, view, tone="red"):
    """A clickable summary card: shows one headline number, the button opens the detail view."""
    with st.container():
        st.markdown(
            f'<div class="drill-card {tone}"><div class="drill-q">{question}</div>'
            f'<div class="drill-title">{title}</div><div class="drill-stat">{stat}</div>'
            f'<div class="drill-sub">{sub}</div></div>', unsafe_allow_html=True)
        st.button("Explore details →", key=f"go_{view}", on_click=go, args=(view,), use_container_width=True)
