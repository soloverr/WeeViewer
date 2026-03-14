@echo off
REM WeeViewer - Build Script
REM This script builds WeeViewer.exe using PyInstaller

echo ========================================
echo WeeViewer Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to install PyInstaller!
        pause
        exit /b 1
    )
)

echo.
echo Building WeeViewer.exe...
echo.

REM Run PyInstaller with the spec file
python -m PyInstaller scripts/viewer.spec --clean

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Build completed successfully!
    echo ========================================
    echo.
    echo Output file: dist\WeeViewer.exe
    echo.
    echo To run WeeViewer, execute: dist\WeeViewer.exe
) else (
    echo.
    echo ========================================
    echo Build failed!
    echo ========================================
    pause
    exit /b 1
)

pause