@echo off
REM JevLocal launcher for Windows.  Usage: double-click, or run  start.bat
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py run.py %*
  goto :eof
)

where python >nul 2>nul
if %errorlevel%==0 (
  python run.py %*
  goto :eof
)

echo Python 3 is required. Install it from https://www.python.org/downloads/ ^(check "Add to PATH"^) and re-run.
pause
