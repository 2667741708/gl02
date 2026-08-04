foreach ($name in 'GL02_PGHOST','GL02_PGPORT','GL02_PGDATABASE','GL02_PGUSER','GL02_PGPASSWORD') {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if ($value) {
        Set-Item -Path "Env:$name" -Value $value
    }
}

python .\tools\audit_22012_recent_8h_pg_pspace.py
