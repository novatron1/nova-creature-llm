@echo off
title Nova Creature — Laptop Full Version
echo ============================================================
echo   NOVA CREATURE — Laptop Full Version
echo   Starting Nova Server...
echo ============================================================
echo.

REM Check for Python
where python3 >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON=python3
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set PYTHON=python
    ) else (
        echo [ERROR] Python is not installed.
        echo Please install Python 3.10+ from https://python.org
        pause
        exit /b 1
    )
)

echo [OK] Found Python: %PYTHON%
%PYTHON% --version

REM Check for required packages
echo [CHECK] Verifying required packages...
%PYTHON% -c "import json, http.server, socketserver, uuid" 2>nul
if %errorlevel% neq 0 (
    echo [INSTALL] Installing required packages...
    %PYTHON% -m pip install --upgrade pip
    if exist requirements-codex.txt (
        %PYTHON% -m pip install -r requirements-codex.txt
    )
)

echo.
echo [START] Launching Nova Server on http://127.0.0.1:3000
echo.

REM Start the server
%PYTHON% nova_web_server.py 3000

if %errorlevel% neq 0 (
    echo [ERROR] Nova server failed to start.
    pause
    exit /b 1
)

pause
