@echo off
call "%~dp0start_robot_runtime.bat" SCANNER
exit /b %errorlevel%
