"""Auto-close logic: the dashboard stops only after the LAST browser tab is gone, never during a long job.
    python -m tests.test_watchdog"""
import os
import sys
import threading

from core import watchdog as w

ok = True
def check(name, cond):
    global ok
    ok &= bool(cond); print('OK  ' if cond else 'FAIL', name)


def run(counts, grace=10.0, busy_at=()):
    """counts: browser sessions seen at t = 0, 2, 4, ... Returns the time of the stop request (or None)."""
    stopped = []
    it = iter(counts)
    cur = {'n': 0}
    watcher = w.Watcher(lambda: cur['n'], lambda: stopped.append(True), grace)
    for i, n in enumerate(counts):
        cur['n'] = n
        t = i * 2.0
        if i in busy_at:
            with w.busy():
                watcher.step(t)
        else:
            watcher.step(t)
        if stopped:
            return t
    return None

check('never opened in a browser: never stops', run([0] * 100) is None)
check('tab open, then closed: stops after the grace period', run([1, 1, 1, 0, 0, 0, 0, 0, 0, 0]) == 16.0)
check('page refresh (a short gap) does not stop it', run([1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1]) is None)
check('two tabs: closing one does not stop it', run([2, 2, 1, 1, 1, 1, 1, 1, 1, 1]) is None)
check('two tabs closed one after the other: stops', run([2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0]) is not None)
check('a long job keeps it alive after the tab is closed', run([1, 0, 0, 0, 0, 0, 0, 0, 0], busy_at=set(range(1, 9))) is None)
t_stop = run([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], busy_at={1, 2, 3, 4})
check('after the job ends the grace period starts again', t_stop is not None and t_stop >= 5 * 2.0 + 10.0 - 2.0)

# busy() is exception-safe and thread-safe
try:
    with w.busy():
        raise RuntimeError('boom')
except RuntimeError:
    pass
check('busy() counter returns to zero after an error', not w.is_busy())
threads = [threading.Thread(target=lambda: [w.busy().__enter__() or None for _ in range(0)]) for _ in range(3)]
with w.busy():
    with w.busy():
        check('nested busy() blocks are counted', w.is_busy())
check('busy() released after nesting', not w.is_busy())

# the long jobs really are wrapped
import tests.smoke_views            # noqa: F401  (streamlit stand-ins)
from pipeline import run_pipeline
seen = []
orig = w.is_busy
import pipeline.run as pr
def probe(*a, **k):
    seen.append(w.is_busy()); return orig()
import pipeline.clean as pc
real_clean = pr.clean
pr.clean = lambda *a, **k: (seen.append(w.is_busy()) or real_clean(*a, **k))
from tests._paths import workbook
from pipeline import load_tables
t, _, _ = load_tables([('w.xlsx', workbook())])
run_pipeline(t['customers'], t['items'], t['orders'])
check('run_pipeline holds the busy flag while it works, and releases it', seen == [True] and not w.is_busy())

# start(): off unless the launcher switches it on; harmless if Streamlit does not offer the session count
os.environ.pop(w.ENV_SWITCH, None)
w._started = False; w.start()
check('without MITSU_AUTO_EXIT the watcher does not start', w._started is False)
os.environ[w.ENV_SWITCH] = '1'
before = threading.active_count()
w._started = False; w._streamlit_session_count = lambda: (_ for _ in ()).throw(AttributeError('no session manager')); w.start()
check('unsupported Streamlit: no thread, no crash', threading.active_count() == before)
sys.exit(0 if ok else 1)
