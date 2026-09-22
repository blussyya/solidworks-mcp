@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "SETUP_EXIT=%ERRORLEVEL%"
echo.
if not "%SETUP_EXIT%"=="0" echo Setup exited with error code %SETUP_EXIT%.
pause
exit /b %SETUP_EXIT%
