@echo off
setlocal
cd /d "%~dp0.."

echo [IMES] Web endpoint:     127.0.0.1:18080/imes.web/
echo [IMES] Vastbase endpoint: 127.0.0.1:15433/vastbase
echo [IMES] Route: local -^> 10.30.220.12 -^> IMES Web + Vastbase
echo [IMES] Keep this window open. Press Ctrl+C to stop both tunnels.
echo.

if defined BF_22012_SSH_PASSWORD (
    python "%~dp0imes_22012_relay.py" --profile imes
) else (
    echo BF_22012_SSH_PASSWORD is not set. Enter the 220.12 SSH password when prompted.
    python "%~dp0imes_22012_relay.py" --prompt-password --profile imes
)

set "RELAY_EXIT=%ERRORLEVEL%"
echo.
if not "%RELAY_EXIT%"=="0" (
    echo [IMES] Tunnel stopped with exit code %RELAY_EXIT%.
    echo Check VPN access to 10.30.220.12:22 and local ports 15433/18080.
) else (
    echo [IMES] Both tunnels stopped.
)
pause
exit /b %RELAY_EXIT%
