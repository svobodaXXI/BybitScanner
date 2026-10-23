@echo off
rem ACCEPTANCE ONLY: runs the stable acceptance checkout (this folder), never C:\BybitScanner.
rem Same ALL intent as the owner desktop button; resolves everything relative to this folder.
echo [ACCEPTANCE] root=%~dp0
call "%~dp0start_robot_runtime.bat" ALL
exit /b %errorlevel%
