$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$bridgePath = Get-ChildItem -LiteralPath (Get-Location).Path -Recurse -Filter "local_pg_ws_bridge.py" | Select-Object -First 1 -ExpandProperty FullName
$bridge = [IO.File]::ReadAllText($bridgePath, [Text.Encoding]::UTF8)
$insert = @'
    if audit_conn is not None:
        try:
            payload["foreman_guidance"] = latest_foreman_guidance(audit_conn)
        except Exception as exc:
            payload["foreman_guidance"] = {"state": "unavailable", "read_only": True, "reason": type(exc).__name__, "fallback_policy": "computed_cold_pressure_when_no_foreman_guidance"}
    return payload


def save_foreman_guidance_request(request: dict[str, Any]) -> dict[str, Any]:
    with psycopg.connect(**pg_params(), row_factory=dict_row) as conn:
        return persist_foreman_guidance(conn, request)


def fetch_diagnosis_history
'@
$pattern = "    return payload\s*\r?\n\r?\ndef fetch_diagnosis_history"
if ($bridge -notmatch "def save_foreman_guidance_request") {
    $bridge = [regex]::Replace($bridge, $pattern, $insert, 1)
    if ($bridge -notmatch "def save_foreman_guidance_request") { throw "bridge payload marker not found" }
}
[IO.File]::WriteAllText($bridgePath, $bridge, $utf8)
Write-Output "bridge guidance insert applied"
