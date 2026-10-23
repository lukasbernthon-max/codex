@echo off
setlocal
cd /d "%~dp0"
echo Installing Focus. Please keep this window open.
echo The first installation needs internet access and may take several minutes.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\windows\install.ps1"
if errorlevel 1 (
    echo.
    echo Installation did not finish. The error above explains what happened.
    echo You can share that error message for help. Never share your API key.
    pause
    exit /b 1
)
echo.
echo Focus is installed. Next time, use the Focus shortcut on your desktop.
pause
