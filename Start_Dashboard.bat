@echo off
setlocal
cd /d "%~dp0"
title Mitsubishi x TNIC Dashboard

rem ---- 1. find a supported Python: 64-bit 3.10 to 3.13 (3.12 preferred) ----
set "PY="
for %%V in (3.12 3.13 3.11 3.10) do (
    if not defined PY (
        py -%%V -c "import struct,sys;sys.exit(0 if struct.calcsize('P')==8 else 1)" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
for %%V in (312 313 311 310) do if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" set PY="%LocalAppData%\Programs\Python\Python%%V\python.exe"
if not defined PY (
    python -c "import struct,sys;sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8 else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :no_python

rem ---- 2. first run: private environment + packages (rebuilt if it is broken) ----
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import streamlit, pandas, plotly, sklearn, openpyxl" >nul 2>nul
    if errorlevel 1 call :remove_venv
)
if exist ".venv\Scripts\streamlit.exe" goto :shortcut

echo.
echo First run: setting up. This takes 2-5 minutes, needs internet, and happens only once.
echo Using:
%PY% --version
if exist ".venv" call :remove_venv
%PY% -m venv .venv
if errorlevel 1 goto :venv_failed
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip install --prefer-binary -r requirements.txt
if errorlevel 1 goto :pip_failed

rem ---- 3. shortcut with the Mitsubishi icon (created once, next to this file) ----
:shortcut
if not exist "%~dp0Mitsubishi TNIC Dashboard.lnk" (
    call :make_shortcut "%~dp0Mitsubishi TNIC Dashboard.lnk"
    echo A shortcut with the Mitsubishi icon was created in this folder. Use it next time.
)

rem ---- 4. start the dashboard (the browser opens by itself) ----
echo.
echo Starting the dashboard. Keep this window open while you present.
echo Closing the browser tab (or the whole browser) stops the dashboard and closes this window.
echo.
set "MITSU_AUTO_EXIT=1"
".venv\Scripts\python.exe" -m streamlit run app.py
if errorlevel 1 pause
exit /b 0

:make_shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%~1'); $s.TargetPath='%~dp0Start_Dashboard.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\img\mitsu_icon_logo.ico'; $s.Description='Mitsubishi x TNIC Dashboard'; $s.Save()" >nul 2>nul
exit /b 0

:remove_venv
rem clear read-only / hidden flags first so the folder can always be deleted
attrib -r -s -h ".venv\*.*" /s /d >nul 2>nul
rmdir /s /q ".venv" >nul 2>nul
exit /b 0

:no_python
echo.
echo This dashboard needs 64-bit Python 3.10 to 3.13. Python 3.12 is recommended.
echo Newer versions (3.14 and later) have no ready-made packages yet, which causes the
echo "Failed to build pyarrow" and "Failed to build pyyaml" errors.
echo.
where winget >nul 2>nul
if errorlevel 1 goto :manual_python
set /p ANS="Install Python 3.12 automatically now? Type Y or N: "
if /i not "%ANS%"=="Y" goto :manual_python
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo Finished. CLOSE this window, then double-click Start_Dashboard.bat again.
pause
exit /b 0

:manual_python
echo Download the Windows 64-bit installer for Python 3.12 from https://www.python.org/downloads/windows/
echo In the installer, tick "Add python.exe to PATH". Then double-click Start_Dashboard.bat again.
pause
exit /b 1

:venv_failed
echo Could not create the private environment. Make sure you can write to this folder.
pause
exit /b 1

:pip_failed
echo.
echo Package installation failed. Python used:
%PY% --version
echo If you see 3.14 or newer, install Python 3.12 and run this file again. Otherwise check the internet connection.
call :remove_venv
pause
exit /b 1
