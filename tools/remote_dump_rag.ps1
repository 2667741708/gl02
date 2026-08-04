$ErrorActionPreference = 'Stop'
$pw = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','Machine')
if (-not $pw) { $pw = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD','User') }
$env:PGPASSWORD = $pw
$dump = 'C:\Windows\Temp\rag_8093_knowledge.dump'
Remove-Item -LiteralPath $dump -Force -ErrorAction SilentlyContinue
& 'F:\PostgreSQL\16\bin\pg_dump.exe' -Fc -h 127.0.0.1 -p 5432 -U gl02_sync -d bf_trend --no-owner --no-privileges --table=bf_assistant.rag_document --table=bf_assistant.rag_chunk --table=bf_assistant.rag_chunk_embedding -f $dump
if ($LASTEXITCODE -ne 0) { throw "pg_dump exit $LASTEXITCODE" }
Get-Item -LiteralPath $dump | Select-Object FullName,Length
