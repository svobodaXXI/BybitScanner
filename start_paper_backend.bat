@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0start_paper_backend.local.bat" call "%~dp0start_paper_backend.local.bat"
if errorlevel 1 (
    echo Failed to load start_paper_backend.local.bat.
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Python venv not found: %~dp0venv\Scripts\python.exe
    exit /b 1
)

"%~dp0venv\Scripts\python.exe" -m terminal.runtime.paper_http_server
