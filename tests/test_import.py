"""First-run welcome screen and the import flow, in an isolated temp data folder.
    python -m tests.test_import"""
import io
import pathlib
import shutil
import sys
import tempfile

import pandas as pd

from tests._paths import workbook
import tests.smoke_views as t            # streamlit stand-ins
fake = t.fake
import config
from core import data as cd
from core.data import data_status, build_dataset
from views import import_data

ok = True
def check(name, cond, extra=''):
    global ok
    ok &= bool(cond); print('OK  ' if cond else 'FAIL', name, extra)


class Upload(io.BytesIO):
    """Looks like Streamlit's UploadedFile."""
    def __init__(self, path):
        super().__init__(pathlib.Path(path).read_bytes()); self.name = pathlib.Path(path).name; self.size = len(self.getvalue())


WB = workbook()                                   # locate the workbook BEFORE the data folder is swapped for a temp one
tmp = pathlib.Path(tempfile.mkdtemp())
config.DATA_DIR, config.PROCESSED_DIR = tmp, tmp / 'processed'
check('empty data folder is not ready', not data_status()['ready'])

# 1. welcome screen with no data and no ctx
fake.session_state.clear(); fake.file_uploader = lambda *a, **k: []
import_data.render(None); check('welcome screen renders without a dataset', True)

# 2. drop the raw tables (the FY2025 workbook holds all three) and process
x = WB
fake.file_uploader = lambda *a, **k: [Upload(x)]
fake.button = lambda *a, **k: k.get('key') == 'imp_run'
fake.rerun_called = False
import_data.render(None)
check('processed dataset written', (tmp / 'final_dataset_main.csv').exists() and (tmp / 'processed' / 'item_master.csv').exists()
      and (tmp / 'processed' / 'processing_report.json').exists())
st_ = data_status(); check('folder is now ready (dataset + master tables)', st_['ready'] and st_['master_source'] == 'processed')
df, items, cust = build_dataset()
check('dashboard data layer reads the processed files', len(df) == 68097 and df['source'].eq('history').all(), f'{len(df):,} rows')
check('status labels are the three dashboard groups', set(df['status'].astype(str)) <= {'Completed', 'On going', 'Loss'}, str(df['status'].value_counts().to_dict()))

# 3. a wrong file is explained, not crashed on
bad = io.BytesIO(b'a,b\n1,2\n'); bad.name, bad.size = 'oops.csv', 8
fake.session_state.clear(); fake.file_uploader = lambda *a, **k: [bad]; fake.button = lambda *a, **k: False
import_data.render(None); check('unrecognised file is reported', any('could not tell' in p or 'Missing' in p for p in fake.session_state['imp_problems']), str(fake.session_state['imp_problems'][:1]))

# 4. the model cards read the report
from core.model_metrics import method_metrics
mm = method_metrics(None, df)
check('pipeline cards show counts from the report', mm['p_clean']['stats'] and mm['p_encode']['stats'], str(mm['p_clean']['stats']))
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)
