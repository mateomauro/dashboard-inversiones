@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python scripts\servidor.py
) else (
  python3 scripts\servidor.py
)
pause
