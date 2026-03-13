@echo off
chcp 65001 >nul
echo [鉴屎官] 正在初始化环境...

:: 创建虚拟环境（若不存在）
if not exist ".venv\Scripts\activate.bat" (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
) else (
    echo [1/3] 虚拟环境已存在，跳过创建
)

:: 激活并安装依赖
echo [2/3] 安装依赖...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt

echo.
echo [3/3] 完成！运行 start.bat 启动程序。
pause
