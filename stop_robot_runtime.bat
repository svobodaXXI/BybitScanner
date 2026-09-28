@echo off
setlocal
cd /d "%~dp0"

set "STOP_LOG=%TEMP%\BybitScanner-stop-last.log"
set "BYBITSCANNER_STOP_DIAGNOSTIC_LOG=%STOP_LOG%"
> "%STOP_LOG%" echo [STOP BAT] START %DATE% %TIME%

if exist "%~dp0start_runtime.local.bat" call "%~dp0start_runtime.local.bat"
if errorlevel 1 (
    echo Failed to load start_runtime.local.bat.
    >> "%STOP_LOG%" echo [STOP BAT] Failed to load start_runtime.local.bat.
    >> "%STOP_LOG%" echo [STOP BAT] EXIT_CODE=1
    echo Diagnostic log: %STOP_LOG%
    pause
    exit /b 1
)

if not exist "%~dp0venv\Scripts\python.exe" (
    echo Python venv not found: %~dp0venv\Scripts\python.exe
    >> "%STOP_LOG%" echo [STOP BAT] Python venv not found: %~dp0venv\Scripts\python.exe
    >> "%STOP_LOG%" echo [STOP BAT] EXIT_CODE=1
    echo Diagnostic log: %STOP_LOG%
    pause
    exit /b 1
)

echo [STOP] Diagnostic log: %STOP_LOG%
"%~dp0venv\Scripts\python.exe" -m tools.stop_robot_runtime
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
)

exit /b %STOP_RC%
