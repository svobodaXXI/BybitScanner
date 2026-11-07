@echo off
rem SwordCounter: compact always-on-top window. Read-only; independent of MetaScalp and the Robot runtime.
rem API key: Windows Credential Manager only, entered in the window (gear button, "Podklyuchenie Bybit").
rem Python: venv next to this repository root, or two levels above it (repository worktree).
setlocal
cd /d "%~dp0..\.."
set "PYW=%CD%\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=%CD%\..\..\venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
    echo Python venv not found next to or two levels above: %CD%
    exit /b 1
)
start "" "%PYW%" -m tools.SwordCounter
exit /b 0
