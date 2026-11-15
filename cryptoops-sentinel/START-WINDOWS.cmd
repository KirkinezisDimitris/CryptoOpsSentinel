@echo off
setlocal
cd /d "%~dp0"
title CryptoOps Sentinel - Local Demo

echo ==============================================
echo          CryptoOps Sentinel - Local
 echo ==============================================
echo.
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python 3.11 or newer is required.
    echo Install Python from https://www.python.org/downloads/windows/
    echo Select "Add python.exe to PATH" during installation.
    pause
    exit /b 1
  )
  set "PYTHON=python"
)
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
if %ERRORLEVEL% NEQ 0 (
  echo ERROR: Python 3.11 or newer is required.
  echo Check your Python version with: py -3 --version
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating an isolated Python environment...
  %PYTHON% -m venv .venv
  if errorlevel 1 goto fail
  echo [2/3] Installing dependencies. This requires internet access the first time...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -e .
  if errorlevel 1 goto fail
) else (
  echo [1/3] Reusing installed local environment.
)
echo [3/3] Starting dashboard...
echo The app should open at http://localhost:8501
echo Close this window or press Ctrl+C to stop.
".venv\Scripts\python.exe" -m streamlit run dashboard\cloud_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo ERROR: Could not start the app. See the error above.
pause
exit /b 1
