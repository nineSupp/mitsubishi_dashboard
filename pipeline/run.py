"""Chain the three stages and write the results."""
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from core.watchdog import busy
from pipeline.clean import clean
from pipeline.encode import encode
from pipeline.log import StepLog
from pipeline.readers import canonicalise
from pipeline.transform import transform


@dataclass
class PipelineResult:
    cleaned: pd.DataFrame
    transformed: pd.DataFrame
    inventory: pd.DataFrame
    final: pd.DataFrame
    log: StepLog
    customers: pd.DataFrame            # standard-named raw master tables (kept for the dashboard)
    items: pd.DataFrame
    seconds: float = 0.0
    summary: dict = field(default_factory=dict)


def run_pipeline(customers, items, orders, progress=None):
    """customers / items / orders: raw DataFrames. progress(fraction, text) is optional (used by the dashboard)."""
    with busy():
        return _run_pipeline(customers, items, orders, progress)


def _run_pipeline(customers, items, orders, progress):
    t0 = time.time()
    say = progress or (lambda f, t: None)
    log = StepLog()
    say(0.05, 'Stage 1 · Cleaning')
    cleaned = clean(customers, items, orders, log)
    say(0.35, 'Stage 2 · Transformation & feature engineering')
    transformed, inventory = transform(cleaned, log)
    say(0.75, 'Stage 3 · Encoding')
    final = encode(transformed, inventory, log)
    say(1.0, 'Done')
    cust_std, _ = canonicalise(customers, 'customers')
    item_std, _ = canonicalise(items, 'items')
    dates = pd.to_datetime(final['Sales Order Date'])
    summary = dict(rows_in=int(len(orders)), rows_out=int(len(final)), columns=int(final.shape[1]),
                   first_date=str(dates.min().date()), last_date=str(dates.max().date()),
                   items=int(final['Item Code'].nunique()), customers=int(final['Customer Internal Id'].nunique()))
    return PipelineResult(cleaned, transformed, inventory, final, log, cust_std, item_std, round(time.time() - t0, 1), summary)


def write_outputs(result, data_dir, csv_name='final_dataset_main.csv'):
    """Save the final dataset (what the dashboard reads), the master tables and a processing report."""
    data_dir = Path(data_dir)
    proc = data_dir / 'processed'
    proc.mkdir(parents=True, exist_ok=True)
    path = data_dir / csv_name
    with busy():
        tmp = path.with_name(path.name + '.tmp')
        result.final.to_csv(tmp, index=False)
        os.replace(tmp, path)                  # the dataset file is never left half-written
    result.items.to_csv(proc / 'item_master.csv', index=False)
    result.customers.to_csv(proc / 'customer_master.csv', index=False)
    report = dict(processed_at=datetime.now().strftime('%Y-%m-%d %H:%M'), seconds=result.seconds, **result.summary,
                  steps=result.log.steps)
    (proc / 'processing_report.json').write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    return path
