@echo off
setlocal
cd /d "%~dp0"

set "STOP_LOG=%TEMP%\BybitScanner-stop-last.log"
> "%STOP_LOG%" echo [STOP BAT] START %DATE% %TIME%

if exist "%~dp0start_runtime.local.bat" call "%~dp0start_runtime.local.bat" >> "%STOP_LOG%" 2>&1
if errorlevel 1 (
    >> "%STOP_LOG%" echo [STOP BAT] Failed to load start_runtime.local.bat.
    >> "%STOP_LOG%" echo [STOP BAT] EXIT_CODE=1
    echo.
    echo [STOP] FAILED while loading local runtime configuration.
    echo [STOP] Diagnostic log: %STOP_LOG%
    echo.
    type "%STOP_LOG%"
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    >> "%STOP_LOG%" echo [STOP BAT] Python venv not found: %~dp0venv\Scripts\python.exe
    >> "%STOP_LOG%" echo [STOP BAT] EXIT_CODE=1
    echo.
    echo [STOP] FAILED: Python venv is missing.
    echo [STOP] Diagnostic log: %STOP_LOG%
    echo.
    type "%STOP_LOG%"
    echo.
    pause
    exit /b 1
)

echo [STOP] Running canonical safe stop.
echo [STOP] Live diagnostic log: %STOP_LOG%
"%~dp0venv\Scripts\python.exe" -m tools.stop_robot_runtime >> "%STOP_LOG%" 2>&1
set "STOP_RC=%ERRORLEVEL%"
>> "%STOP_LOG%" echo [STOP BAT] EXIT_CODE=%STOP_RC%

if not "%STOP_RC%"=="0" (
    echo.
    echo [STOP] FAILED with exit code %STOP_RC%.
    echo [STOP] Diagnostic log: %STOP_LOG%
    echo.
    type "%STOP_LOG%"
    echo.
    pause
    exit /b %STOP_RC%
)

echo [STOP] SUCCESS. Diagnostic log: %STOP_LOG%
exit /b 0
