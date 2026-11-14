@echo off
setlocal
where py >nul 2>&1
if errorlevel 1 (
  echo Python Launcher py.exe is required. Install Python 3 with Tkinter.
  pause
  exit /b 1
)
py -3 "%~dp0windows_vps_manager.py"
if errorlevel 1 (
  echo VPS Manager could not start. Check Python and Tkinter installation.
  pause
  exit /b 1
)
