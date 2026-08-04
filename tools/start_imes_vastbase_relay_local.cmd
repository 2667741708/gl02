@echo off
setlocal
cd /d "%~dp0.."

echo [IMES] Local endpoint: 127.0.0.1:15433
echo [IMES] Route: local -^> 10.30.220.12 -^> 10.10.181.195:5432
echo [IMES] Keep this window open. Press Ctrl+C to stop the tunnel.
echo.

if defined BF_22012_SSH_PASSWORD (
    python "%~dp0imes_22012_relay.py" --forward "imes_vastbase:15433:10.10.181.195:5432"
) else (
    echo BF_22012_SSH_PASSWORD is not set. Enter the 220.12 SSH password when prompted.
    python "%~dp0imes_22012_relay.py" --prompt-password --forward "imes_vastbase:15433:10.10.181.195:5432"
)

set "RELAY_EXIT=%ERRORLEVEL%"
echo.
if not "%RELAY_EXIT%"=="0" (
    echo [IMES] Tunnel stopped with exit code %RELAY_EXIT%.
    echo Check VPN access to 10.30.220.12:22 and whether local port 15433 is already occupied.
) else (
    echo [IMES] Tunnel stopped.
)
pause
exit /b %RELAY_EXIT%
