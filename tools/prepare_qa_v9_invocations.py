"""Bind V9 invocations to reviewed file hashes; does not execute them."""
from pathlib import Path
import hashlib
import argparse
ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".codex_runtime/qa-routing-v9/release"
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=("v9", "v10", "v11", "v12", "v13", "v14", "v15", "v16", "v17", "v18", "v19", "v20", "v21", "v22", "v23", "v24", "v25", "v26", "v52"), default="v9")
    args = parser.parse_args()
    RELEASE = ROOT / f".codex_runtime/qa-routing-{args.version}/release"
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
    text = text.replace("v8", args.version).replace("V8", args.version.upper())
    if args.version == "v52":
        text = text.replace("qa-routing-v52-20260916-r1", "qa-routing-v52-20260921-r1")
    (RELEASE / "invoke-deployment.ps1").write_text(text, encoding="utf-8", newline="\n")
    record = (ROOT / ".codex_runtime/qa-routing-v8/release/invoke-record.ps1").read_text(encoding="utf-8")
    record = record.replace("v8", args.version).replace("V8", args.version.upper())
    if args.version == "v52":
        record = record.replace("qa-routing-v52-20260916-r1", "qa-routing-v52-20260921-r1")
    (RELEASE / "invoke-record.ps1").write_text(record, encoding="utf-8", newline="\n")
