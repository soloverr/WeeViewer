@echo off
REM WeeViewer - Install Dependencies
REM This script installs all required Python dependencies

echo ========================================
echo WeeViewer Dependency Installation
echo ========================================
echo.

echo Installing dependencies from requirements.txt...
pip install -r requirements.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Installation completed successfully!
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Installation failed!
    echo ========================================
    exit /b 1
)

echo.
echo To run WeeViewer, execute: python run.py
pause