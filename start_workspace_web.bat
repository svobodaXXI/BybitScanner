@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_workspace_web.ps1" -Build %*
if errorlevel 1 (
  echo Web workspace launch failed. Scanner and Robot were not started.
  pause
  exit /b 1
)
echo Local web workspace launch requested. No Scanner or Robot started.
exit /b 0
