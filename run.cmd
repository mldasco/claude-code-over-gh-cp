@echo off
setlocal

if exist venv\Scripts\python.exe (
  venv\Scripts\python.exe scripts\run.py %*
) else (
  python scripts\run.py %*
)

exit /b %errorlevel%
