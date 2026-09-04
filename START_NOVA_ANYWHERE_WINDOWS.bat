@echo off
setlocal
title Nova Creature - Private Phone Access
cd /d "%~dp0"

echo ============================================================
echo   NOVA CREATURE - PC + PRIVATE PHONE ACCESS
echo ============================================================
echo.

REM Find Python 3.10 or newer without trusting a Windows Store alias.
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON=python"
    ) else (
        python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON=python3"
        ) else (
            echo [ERROR] Python 3.10 or newer is not installed.
            echo Please install Python from https://python.org
            pause
            exit /b 1
        )
    )
)

if exist "F:\Nova\kokoro-tts\.venv\Scripts\python.exe" set "PYTHON=F:\Nova\kokoro-tts\.venv\Scripts\python.exe"

echo [OK] Found Python: %PYTHON%
%PYTHON% --version

REM Install only Nova's small runtime helpers when they are missing.
%PYTHON% -c "import qrcode, qrcode.image.svg, cryptography, PIL" 2>nul
if %errorlevel% neq 0 (
    if exist "%~dp0requirements-runtime.txt" (
        echo [INSTALL] Adding Nova runtime helpers...
        %PYTHON% -m pip install -r "%~dp0requirements-runtime.txt"
        if %errorlevel% neq 0 (
            echo [ERROR] Nova runtime helpers could not be installed.
            pause
            exit /b 1
        )
    )
)

echo.
echo [START] Preparing private phone access...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_nova_kokoro_voice.ps1" -ProjectRoot "%~dp0."
%PYTHON% "%~dp0tools\nova_anywhere.py" --root "%~dp0." --port 3000 --https-port 8443
if %errorlevel% neq 0 (
    echo [ERROR] Nova Anywhere did not start. Read the message above, then try again.
    pause
    exit /b 1
)

endlocal
