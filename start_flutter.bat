@echo off
cd /d "%~dp0flutter_app"

set EXE=build\windows\x64\runner\Release\bullshit_detector.exe

if not exist "%EXE%" (
    flutter build windows --release
    if %errorlevel% neq 0 ( pause & exit /b 1 )
)

start "" "%EXE%"
