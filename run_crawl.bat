@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
".venv\Scripts\python.exe" main.py >> logs\crawl.log 2>&1
