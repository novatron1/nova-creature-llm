@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INSTALL_NOVA_GPU_HUB_WINDOWS.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo [ERROR] Nova GPU Hub setup failed.
    pause
)
exit /b %EXITCODE%
