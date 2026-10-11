@echo off
rem SwordCounter: setup of the separate Read-Only Bybit key. The key is typed into hidden prompts
rem and saved to the Windows Credential Manager. This file holds no key, no secret, no variable.
setlocal
cd /d "%~dp0..\.."
set "PY=%CD%\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%CD%\..\..\venv\Scripts\python.exe"
if not exist "%PY%" (
    echo Python venv not found next to or two levels above: %CD%
    pause
    exit /b 1
)
"%PY%" -m tools.SwordCounter.setup_keys %*
echo.
pause
exit /b %errorlevel%
