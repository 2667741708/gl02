[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:GL02_PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGADMIN_PASSWORD", "Machine")
$dbUser = [Environment]::GetEnvironmentVariable("GL02_PGADMIN_USER", "Machine")
if ([string]::IsNullOrWhiteSpace($dbUser)) { $dbUser = "postgres" }
& "C:\Program Files\Python311\python.exe" "C:\Users\Administrator\AppData\Local\Temp\analyze_p_blast_cold_history.py" --host 127.0.0.1 --port 5432 --database bf_trend --user $dbUser --days 7 --out-prefix "C:\Users\Administrator\AppData\Local\Temp\p_blast_cold_history_analysis_7d"
if ($LASTEXITCODE -ne 0) { throw "P_blast_cold 7-day analysis failed" }
