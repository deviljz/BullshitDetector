@echo off
echo [BullshitDetector] Setting up environment...

if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment already exists, skipping.
)

echo [2/3] Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt

echo [3/3] Installing Playwright browser (Chromium)...
playwright install chromium

echo.
echo Done! Run start.bat to launch.
pause
