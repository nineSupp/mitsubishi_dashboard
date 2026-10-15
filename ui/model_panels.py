"""Model strip (shown at the top of each view) and the model map (which model powers what)."""
import pandas as pd
import streamlit as st

from core.model_metrics import method_metrics
from core.model_registry import FEATURES, METHODS, TESTED_ONLY


def _flat(html):
    # no indentation / blank lines: 4+ leading spaces would turn the HTML into a Markdown code block
    return "\n".join(line.strip() for line in html.splitlines() if line.strip())


def model_strip(feature, ctx=None):
    """Dark banner shown on every page: each model/method with its description, what it does on this page and its accuracy."""
    f = FEATURES[feature]
    metrics = method_metrics(ctx.outputs, ctx.df_all) if ctx is not None else {}
    cards = []
    for k, why in f['models']:
        m, mm = METHODS[k], metrics.get(k, dict(stats=[], note=''))
        stats = "".join(f'<div class="mc-stat"><span>{lab}</span><b>{val}</b></div>' for lab, val in mm['stats'])
        acc = (f'<div class="mc-acc">{stats}</div>' if stats else '<div class="mc-acc"><div class="mc-stat"><span>Accuracy</span><b>Not scored</b></div></div>')
        cards.append(
            f'<div class="model-card"><div class="mc-head"><span class="mc-name">{m["icon"]} {m["name"]}</span><em>{m["kind"]}</em></div>'
            f'<div class="mc-desc">{m["how"]}</div><div class="mc-does"><b>What it does here:</b> {why}</div>{acc}'
            f'<div class="mc-note">{mm["note"]}</div></div>')
    st.markdown(_flat('<div class="model-strip"><div class="model-strip-title">Models on this page · description, role and accuracy</div>'
                      '<div class="model-grid">' + "".join(cards) + '</div></div>'), unsafe_allow_html=True)


def _acc(ev, model, level, fold):
    if ev is None or model is None:
        return "n/a (no forecast model)"
    s = ev[(ev['Model'] == model) & (ev['Level'] == level) & (ev['Target'] == 'Revenue') & (ev['Fold'] == fold)]['Accuracy']
    return f"{s.iloc[0] * 100:.0f}%" if len(s) else "–"


def model_map(ev=None):
    """Table: dashboard feature -> method -> what it does -> accuracy (validation FY2024 / final test FY2025)."""
    rows = []
    for fkey, f in FEATURES.items():
        for mkey, why in f['models']:
            m = METHODS[mkey]
            rows.append(f'<tr><td class="mm-feature">{f["title"]}</td><td class="mm-model">{m["icon"]} {m["name"]}</td>'
                        f'<td>{m["kind"]}</td><td>{why}</td><td class="mm-num">{_acc(ev, m["eval_name"], m["eval_level"], "FY2024")}</td>'
                        f'<td class="mm-num">{_acc(ev, m["eval_name"], m["eval_level"], "FY2025")}</td></tr>')
    html = ('<div class="model-map"><table><thead><tr><th>Feature</th><th>Model / method</th><th>Type</th><th>Used for</th>'
            '<th>Validation FY2024</th><th>Final test FY2025</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')
    st.markdown(_flat(html), unsafe_allow_html=True)
    st.caption("Accuracy = 1 − WAPE on revenue (company × month for Gradient Boosting, category × month for the sales-mix split). "
               "Rule-based and statistical methods have no forecast to score. RandomForest, LightGBM, XGBoost and Hurdle were tested too: see Model Accuracy.")


def tested_only_table():
    return pd.DataFrame({"Model tested": list(TESTED_ONLY), "Why it is not used": list(TESTED_ONLY.values())})


def team_models_panel(ev):
    """Dark cards for RandomForest, LightGBM, XGBoost and Hurdle: description from the team slide + real scores."""
    from core.model_metrics import team_model_rows
    rows, flat = team_model_rows(ev)
    pct = lambda v: "–" if v is None else f"{v * 100:.0f}%"        # noqa: E731
    cards = []
    for r in rows:
        if r['ran']:
            stats = (f'<div class="mc-stat"><span>Item units · validation FY2024</span><b>{pct(r["units_val"])}</b></div>'
                     f'<div class="mc-stat"><span>Item units · final FY2025</span><b>{pct(r["units_final"])}</b></div>'
                     f'<div class="mc-stat"><span>Category revenue* · validation</span><b>{pct(r["cat_val"])}</b></div>'
                     f'<div class="mc-stat"><span>Category revenue* · final</span><b>{pct(r["cat_final"])}</b></div>')
            note_ = "Not used as the dashboard default: the recent-sales mix scored higher on category revenue in validation."
        else:
            stats = '<div class="mc-stat"><span>Score</span><b>Not run in this build</b></div>'
            note_ = f"Install it (pip install {r['name'].lower()}), run scripts.evaluate_models, then set ITEM_MIX_MODEL = '{r['config']}' in config.py to use it."
        cards.append(f'<div class="model-card"><div class="mc-head"><span class="mc-name">{r["name"]}</span><em>Quantity model</em></div>'
                     f'<div class="mc-desc">{r["desc"]}</div><div class="mc-acc">{stats}</div><div class="mc-note">{note_}</div></div>')
    base = (f'Benchmark, recent-sales mix: item units {pct(flat["units_val"])} / {pct(flat["units_final"])}, '
            f'category revenue {pct(flat["cat_val"])} / {pct(flat["cat_final"])} (validation / final). '
            '*Category revenue accuracy when the model splits the Gradient Boosting company forecast across items.')
    st.markdown(_flat('<div class="model-strip"><div class="model-strip-title">Your team\'s four quantity-forecasting models, tested</div>'
                      '<div class="model-grid">' + "".join(cards) + f'</div><div class="mc-note" style="margin-top:0.6rem">{base}</div></div>'),
                unsafe_allow_html=True)
