"""Execute the actual deployment GET gate with delayed/failed readiness fixtures."""
from pathlib import Path
import subprocess
import json
import pytest
ROOT = Path(__file__).resolve().parents[1]
PWSH = Path("C:/Program Files/PowerShell/7/pwsh.exe")

@pytest.mark.parametrize("mode,ready,count", [("immediate",True,1),("delayed",True,2),("persistent",False,3),("exception",False,3)])
def test_actual_guard_get_gate_is_bounded_and_never_posts(tmp_path, mode, ready, count):
    text = (ROOT / "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1").read_text(encoding="utf-8")
    start = text.index("function Read-QaReadiness {")
    end = text.index("function Protected-Map", start)
    function = text[start:end]
    assert "POST" not in function.upper() and "-TimeoutSec 10" in function
    fixture = '''
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'Core7 required' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
$script:Calls = 0
function Invoke-RestMethod {
    param($Uri,$TimeoutSec)
    $script:Calls++
    if ($Uri -ne 'http://127.0.0.1:8093/api/ollama/status' -or $TimeoutSec -ne 10) { throw 'Unexpected endpoint' }
    if ($Mode -eq 'exception') { throw 'secret-must-not-appear' }
    $Model = ($Mode -eq 'immediate' -or ($Mode -eq 'delayed' -and $script:Calls -gt 1))
    return [pscustomobject]@{ proxy_ok=$true; ollama_ok=$true; model_ok=$Model; error='secret-must-not-appear' }
}
'''
    path = tmp_path / "readiness-fixture.ps1"
    path.write_text("$Mode = '" + mode + "'\n" + fixture + function + "\nRead-QaReadiness | ConvertTo-Json -Depth 5\n", encoding="utf-8",newline="\n")
    result = subprocess.run([str(PWSH),"-NoLogo","-NoProfile","-File",str(path)],capture_output=True,text=True,encoding="utf-8",check=True)
    payload = json.loads(result.stdout)
    assert payload["ready"] is ready and len(payload["checks"]) == count
    assert "secret-must-not-appear" not in result.stdout
