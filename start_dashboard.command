#!/bin/bash
# Mac / Linux launcher: double-click (Mac: right-click > Open the first time) or run ./start_dashboard.command
cd "$(dirname "$0")"
PY=""
for v in python3.12 python3.13 python3.11 python3.10 python3; do
  p=$(command -v $v) || continue
  "$p" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" && { PY="$p"; break; }
done
if [ -z "$PY" ]; then echo "Needs Python 3.10 to 3.13 (3.12 recommended). Newer versions lack ready-made packages. Install from https://www.python.org/downloads/"; read -p "Press Enter to close"; exit 1; fi
if [ -x ".venv/bin/python" ] && ! .venv/bin/python -c "import streamlit, pandas, plotly, sklearn, openpyxl" 2>/dev/null; then rm -rf .venv; fi
if [ ! -x ".venv/bin/python" ]; then
  echo "First run: setting up with $("$PY" --version) (2-5 minutes, needs internet)..."
  "$PY" -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install --prefer-binary -r requirements.txt || { echo "Setup failed."; rm -rf .venv; read -p "Press Enter to close"; exit 1; }
fi
echo "Starting the dashboard. Closing the browser tab stops it."
export MITSU_AUTO_EXIT=1
.venv/bin/python -m streamlit run app.py
