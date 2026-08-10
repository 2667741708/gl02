$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$bridgePath = Get-ChildItem -LiteralPath (Get-Location).Path -Directory | ForEach-Object { Get-ChildItem -LiteralPath $_.FullName -Filter "local_pg_ws_bridge.py" -File -ErrorAction SilentlyContinue } | Select-Object -First 1 -ExpandProperty FullName
if (-not $bridgePath) { throw "direct bridge file not found" }
$bridge = [IO.File]::ReadAllText($bridgePath, [Text.Encoding]::UTF8)
$anchor = "def fetch_diagnosis_history"
$pos = $bridge.IndexOf($anchor, [StringComparison]::Ordinal)
if ($pos -lt 0) { throw "bridge diagnosis history anchor missing" }
if ($bridge.IndexOf("def save_foreman_guidance_request", [StringComparison]::Ordinal) -lt 0) {
    $insert = @'
def save_foreman_guidance_request(request: dict[str, Any]) -> dict[str, Any]:
    with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
        return persist_foreman_guidance(conn, request)


'@
    $bridge = $bridge.Substring(0, $pos) + $insert + $bridge.Substring($pos)
}
if ($bridge.IndexOf('payload["foreman_guidance"]', [StringComparison]::Ordinal) -lt 0) {
    $fn = $bridge.IndexOf("def diagnosis_snapshot_payload", [StringComparison]::Ordinal)
    $ret = $bridge.IndexOf("    return payload", $fn, [StringComparison]::Ordinal)
    if ($fn -lt 0 -or $ret -lt 0) { throw "diagnosis payload return anchor missing" }
    $insertPayload = @'
    if audit_conn is not None:
        try:
            payload["foreman_guidance"] = latest_foreman_guidance(audit_conn)
        except Exception as exc:
            payload["foreman_guidance"] = {"state": "unavailable", "read_only": True, "reason": type(exc).__name__, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
'@
    $bridge = $bridge.Substring(0, $ret) + $insertPayload + [Environment]::NewLine + $bridge.Substring($ret)
}
[IO.File]::WriteAllText($bridgePath, $bridge, $utf8)
Write-Output $bridgePath
