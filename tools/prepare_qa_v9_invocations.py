"""Bind V9 invocations to reviewed file hashes; does not execute them."""
from pathlib import Path
import hashlib
ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".codex_runtime/qa-routing-v9/release"
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

if __name__ == "__main__":
    text = (ROOT / ".codex_runtime/qa-routing-v8/release/invoke-deployment.ps1").read_text(encoding="utf-8")
    replacements = {
        "15D44FCDBD1B48370CA0B9A536B8A1C379DFF1830CF7C449FF943D21F451D4B1": sha(ROOT / "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1"),
        "2F75BC19FDD3DF35FBF39978B33A240E10A4014EEFAD9DDF9AC8204B44495661": sha(RELEASE / "delta-plan.json"),
        "2BC89761F6DCFE6B9CDD8281599D4D8E53E7DB2DA69287ACF10B56D6899614A5": sha(RELEASE / "scope-gate.json"),
    }
    for old, new in replacements.items():
        if text.count(old) != 1:
            raise ValueError("Invocation binding seam changed")
        text = text.replace(old, new)
    (RELEASE / "invoke-deployment.ps1").write_text(text.replace("v8", "v9").replace("V8", "V9"), encoding="utf-8", newline="\n")
    record = (ROOT / ".codex_runtime/qa-routing-v8/release/invoke-record.ps1").read_text(encoding="utf-8")
    (RELEASE / "invoke-record.ps1").write_text(record.replace("v8", "v9").replace("V8", "V9"), encoding="utf-8", newline="\n")
