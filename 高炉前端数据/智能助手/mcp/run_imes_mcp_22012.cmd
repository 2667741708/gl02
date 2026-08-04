@echo off
setlocal
rem Trusted 220.12 deployment: direct, fixed Vastbase target; stdio only.
set "IMES_MCP_CONNECTION_MODE=direct_22012"
set "IMES_RELAY_DB_HOST=10.10.181.195"
set "IMES_RELAY_DB_PORT=5432"
set "MCP_TRANSPORT=stdio"
"C:\Program Files\Python311\python.exe" -X utf8 "%~dp0imes_relay_mcp_server.py"
