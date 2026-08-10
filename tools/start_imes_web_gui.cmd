@echo off
setlocal
set "ROOT=%~dp0.."
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
  start "IMES Web 本地转发" pythonw.exe "%~dp0imes_web_launcher.py"
  exit /b 0
)
python.exe "%~dp0imes_web_launcher.py"
