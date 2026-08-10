$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding($false)
$bridgePath = Get-ChildItem -LiteralPath (Get-Location).Path -Recurse -Filter "local_pg_ws_bridge.py" | Select-Object -First 1 -ExpandProperty FullName
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
[IO.File]::WriteAllText($bridgePath, $bridge, $utf8)
Write-Output "bridge save helper inserted"
