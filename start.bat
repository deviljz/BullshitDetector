@echo off
if not exist ".venv\Scripts\activate.bat" (
    echo [Error] Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -X utf8 src\main.py
