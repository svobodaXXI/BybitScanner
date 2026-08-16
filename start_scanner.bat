@echo off
cd /d C:\BybitScanner

start "BybitScanner - Telegram Review" powershell.exe -NoExit -Command "Set-Location 'C:\BybitScanner'; python telegram_review.py"

timeout /t 2 /nobreak >nul

start "BybitScanner - Scanner" powershell.exe -NoExit -Command "Set-Location 'C:\BybitScanner'; python main.py"

exit
