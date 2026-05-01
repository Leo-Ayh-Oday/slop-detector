@echo off
echo ================================
echo   Codebase Q&amp;A
echo ================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found
echo.
echo Installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies ready
echo.
echo ================================
echo Server starting...
echo Open http://localhost:8766
echo Press Ctrl+C to stop
echo ================================
echo.
python server.py
pause
