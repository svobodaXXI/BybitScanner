@echo off
rem SwordCounter: compact always-on-top window. Read-only; independent of MetaScalp and the Robot runtime.
rem API keys: user environment variables SWORDCOUNTER_BYBIT_API_KEY / SWORDCOUNTER_BYBIT_API_SECRET.
setlocal
cd /d "%~dp0..\.."
if not exist "venv\Scripts\pythonw.exe" (
    echo Python venv not found: %CD%\venv\Scripts\pythonw.exe
    exit /b 1
)
start "" "venv\Scripts\pythonw.exe" -m tools.SwordCounter
exit /b 0
