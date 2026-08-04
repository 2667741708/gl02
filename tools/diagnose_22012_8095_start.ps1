$ErrorActionPreference = "Continue"
$backend = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\智能助手\backend\ollama_proxy_server_8095.py"
$out = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\diagnose_8095_start.log"
"$(Get-Date -Format o) begin" | Set-Content -LiteralPath $out -Encoding UTF8
& "C:\Program Files\Python311\python.exe" -c "import ast,pathlib; ast.parse(pathlib.Path(r'$backend').read_text(encoding='utf-8')); print('AST_OK')" *>> $out
"python_exit=$LASTEXITCODE" | Add-Content -LiteralPath $out -Encoding UTF8
Get-Item -LiteralPath $backend | Format-List FullName,Length,LastWriteTime | Out-File -FilePath $out -Append -Encoding UTF8
