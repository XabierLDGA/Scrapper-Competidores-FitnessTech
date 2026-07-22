@echo off
cd /d "%~dp0"

netstat -ano | findstr ":5000" | findstr "LISTENING" >nul
if errorlevel 1 (
    start "Competitor Monitor Dashboard" /min ".venv\Scripts\python.exe" dashboard.py
    timeout /t 3 /nobreak >nul
)

explorer.exe "http://localhost:5000"
