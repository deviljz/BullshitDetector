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
echo [3/5] Generating icon...
python create_icon.py
if errorlevel 1 (
    echo [ERROR] Icon generation failed
    pause & exit /b 1
)

echo.
echo [4/5] Cleaning old build artifacts...
if exist dist\BullshitDetector.exe del /f /q dist\BullshitDetector.exe
if exist build rmdir /s /q build

echo.
echo [5/5] Packaging with PyInstaller...
pyinstaller BullshitDetector.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed, check output above
    pause & exit /b 1
)

echo.
echo [+] Copying config sample and docs...
copy /y config.json.example dist\config.json.example >nul
if not exist dist\docs mkdir dist\docs
copy /y docs\USAGE.md dist\docs\USAGE.md >nul
copy /y docs\API_KEYS.md dist\docs\API_KEYS.md >nul

echo.
echo ============================================
echo  Done! Output: dist\BullshitDetector.exe
echo  dist\ contents:
echo    BullshitDetector.exe
echo    config.json.example  ^<-- copy to config.json and fill keys
echo    docs\USAGE.md
echo    docs\API_KEYS.md
echo  Copy your config.json to dist\ before run.
echo ============================================
echo.
pause
