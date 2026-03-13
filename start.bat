@echo off
chcp 65001 >nul

if not exist ".venv\Scripts\activate.bat" (
    echo [错误] 未找到虚拟环境，请先运行 setup.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
cd src
python -X utf8 main.py
