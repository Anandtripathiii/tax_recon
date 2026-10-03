@echo off
echo Installing Python packages (first run only, takes about a minute)...
py -m pip install --quiet -r requirements.txt
echo.
echo Starting Tax Reconciliation. Your browser will open at http://127.0.0.1:5000
echo Press Ctrl+C in this window to stop.
echo.
py app.py
pause
