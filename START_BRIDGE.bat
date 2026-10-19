@echo off
title ChatGPT x Antigravity Bridge [Static Tunnel]
cd /d "%~dp0"

:: ==============================================================================
:: Configuration: Target local port & ngrok free static domain
:: ==============================================================================
if "%PORT%"=="" set PORT=8000
if "%NGROK_DOMAIN%"=="" set NGROK_DOMAIN=jab-jingling-come.ngrok-free.dev

python -u scripts\run_static_bridge.py
if errorlevel 1 (
    echo.
    echo [ERROR] The Bridge exited with an error. Check logs above.
    pause
)
