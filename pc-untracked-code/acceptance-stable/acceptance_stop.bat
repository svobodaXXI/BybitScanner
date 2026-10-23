@echo off
rem ACCEPTANCE ONLY: canonical safe stop of the acceptance checkout (this folder).
echo [ACCEPTANCE] root=%~dp0
call "%~dp0stop_robot_runtime.bat"
exit /b %errorlevel%
