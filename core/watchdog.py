"""Stop the dashboard when the last browser tab is closed, so the launcher window closes too.

Off by default. The launchers (Start_Dashboard.bat, start_dashboard.command) switch it on with MITSU_AUTO_EXIT=1,
so running `streamlit run app.py` by hand, or hosting the app elsewhere, is never affected.

How it works: a background thread asks Streamlit how many browser sessions are connected every 2 seconds.
When there have been none for GRACE seconds (long enough to survive a page refresh) it stops the process.
It never stops the app while a long job (import, retrain) is running: wrap such work in `with busy():`.
No Streamlit imports at module level, so the data pipeline can use busy() without needing Streamlit."""
import contextlib
import os
import threading
import time

ENV_SWITCH = "MITSU_AUTO_EXIT"
GRACE = float(os.environ.get("MITSU_EXIT_GRACE", "10"))       # seconds with no browser before stopping
INTERVAL = 2.0

_busy = 0
_lock = threading.Lock()
_started = False


@contextlib.contextmanager
def busy():
    """Keep the dashboard alive while a long job runs, even if the browser tab is closed meanwhile."""
    global _busy
    with _lock:
        _busy += 1
    try:
        yield
    finally:
        with _lock:
            _busy -= 1


def is_busy():
    with _lock:
        return _busy > 0


class Watcher:
    """The decision logic (separate from Streamlit so it can be tested)."""

    def __init__(self, count, on_exit, grace=GRACE):
        self.count, self.on_exit, self.grace = count, on_exit, grace
        self.seen = False            # has a browser connected at least once?
        self.zero_since = None

    def step(self, now):
        """One check. Returns True when it asked the app to stop."""
        if self.count() > 0:
            self.seen, self.zero_since = True, None
            return False
        if not self.seen or is_busy():             # never opened yet, or a long job is running
            self.zero_since = None
            return False
        if self.zero_since is None:
            self.zero_since = now
        if now - self.zero_since >= self.grace:
            self.on_exit()
            return True
        return False


def _streamlit_session_count():
    from streamlit.runtime import Runtime
    mgr = Runtime.instance()._session_mgr
    if hasattr(mgr, "num_active_sessions"):
        return int(mgr.num_active_sessions())
    return len(list(mgr.list_active_sessions()))


def _stop():
    print("\nThe browser was closed. Stopping the dashboard...", flush=True)
    os._exit(0)


def start():
    """Start the watcher once per process, only when the launcher switched it on."""
    global _started
    if _started or os.environ.get(ENV_SWITCH) != "1":
        return
    _started = True
    try:
        _streamlit_session_count()                              # is this Streamlit version supported?
    except Exception:                                           # noqa: BLE001
        print("Auto-close is not available with this Streamlit version. Close this window to stop the dashboard.", flush=True)
        return
    w = Watcher(_streamlit_session_count, _stop)

    def loop():
        while True:
            time.sleep(INTERVAL)
            try:
                w.step(time.monotonic())
            except Exception:                                   # noqa: BLE001
                return                                          # never break the app because of the watcher

    threading.Thread(target=loop, daemon=True, name="mitsu-auto-exit").start()
    print(f"Auto-close is on: closing the browser tab stops the dashboard (after {GRACE:g} seconds).", flush=True)
