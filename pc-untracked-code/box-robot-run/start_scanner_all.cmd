@echo off
cd /d C:\BybitScanner-box-robot-run

set BYBITSCANNER_IKIGAI_BOX_SIGNALS=1
set BYBITSCANNER_IKIGAI_BOX_WATCH=1

"C:\BybitScanner\venv\Scripts\python.exe" -u main.py
pause
