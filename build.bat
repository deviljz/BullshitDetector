@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  BullshitDetector build script
echo ============================================

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+
    pause & exit /b 1
)

echo.
echo [1/4] Recreating virtual environment...
if exist .venv rmdir /s /q .venv
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create venv
    pause & exit /b 1
)

echo.
echo [2/4] Installing dependencies...
call .venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt pyinstaller --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed
    pause & exit /b 1
)

echo.
echo [3/4] Cleaning old build artifacts...
if exist dist\BullshitDetector.exe del /f /q dist\BullshitDetector.exe
if exist build rmdir /s /q build

echo.
echo [4/4] Packaging with PyInstaller...
pyinstaller BullshitDetector.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed, check output above
    pause & exit /b 1
)

echo.
echo ============================================
echo  Done! Output: dist\BullshitDetector.exe
echo  Copy your config.json to dist\ before run.
echo ============================================
echo.
pause
