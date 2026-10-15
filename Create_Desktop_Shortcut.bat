@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Mitsubishi TNIC Dashboard.lnk'); $s.TargetPath='%~dp0Start_Dashboard.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0assets\img\mitsu_icon_logo.ico'; $s.Description='Mitsubishi x TNIC Dashboard'; $s.Save()"
if errorlevel 1 (
    echo Could not create the desktop shortcut.
) else (
    echo Done. A "Mitsubishi TNIC Dashboard" icon is now on your desktop.
)
pause
