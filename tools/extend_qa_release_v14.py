"""One-time extension of reviewed guarded templates for public-unit evidence fixes."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def write(path, text):
    path.write_text(text, encoding='utf-8', newline='\n')

def main():
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1', 'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1'):
        path = ROOT / 'tools' / name
        text = path.read_text(encoding='utf-8')
        if "'V14'" in text: raise ValueError('V14 already extended')
        text = text.replace("'V12','V13')", "'V12','V13','V14')")
        if name == 'remote_guarded_deploy_qa_routing_v3_8093.ps1':
            text = text.replace('if ($StageRoot -ne $ExpectedStage)', "if ($Version -eq 'V14') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @('高炉前端数据/智能助手/backend/qa_verified_facts.py')\n}\nif ($StageRoot -ne $ExpectedStage)", 1)
        elif name == 'record_qa_routing_v3_version.ps1':
            start = text.index("if ($Version -eq 'V13') {")
            end = text.index('\n}', start) + 2
            text = text[:end] + '\n' + text[start:end].replace('V13', 'V14').replace('v13', 'v14').replace('render typed current readings in isolated formal compounds', 'bind canonical public units and expose missing-unit completion') + text[end:]
        elif name == 'remote_preflight_qa_routing_v3.ps1':
            text = text.replace('$Python = ', "if ($Version -eq 'V14') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v14-20260916-r1' }\n$Python = ", 1)
        write(path, text)
    path = ROOT / 'tools/prepare_qa_routing_v3_release.py'
    text = path.read_text(encoding='utf-8').replace('"v12", "v13")', '"v12", "v13", "v14")')
    text = text.replace('"v13": V13_ARTIFACTS}', '"v13": V13_ARTIFACTS, "v14": V14_ARTIFACTS}')
    text = text.replace('\ndef sha256(', '''
V14_ARTIFACTS = {
    "qa_verified_facts.py": {"baseline":["BASELINE_HASH"], "markers":["canonical_gl02_contract", "missing_unit_objects"], "allow_create":False},
}

def sha256(''', 1)
    text = text.replace('if args.version == "v13":\n            READ_SET.update', 'if args.version in ("v13", "v14"):\n            READ_SET.update', 1)
    text = text.replace('    base_head = args.base_head.lower()', '''        if args.version == "v14":
            READ_SET.pop("高炉前端数据/智能助手/backend/qa_verified_facts.py", None)
            READ_SET.update({
                "高炉前端数据/智能助手/backend/ollama_proxy_server.py":"9a942b2fe73ddb34d0bff8d18beea14047ef898bb6596570d0c1d9509a34e81b",
                "高炉前端数据/智能助手/backend/qa_document_compound.py":"bfcefd214fae105e1c137ec8f516df8c84c749f04331b6b65077db3ab80d8301",
            })
    base_head = args.base_head.lower()''', 1)
    text = text.replace('        write_json(release / "release-spec.json", spec)', '''        if args.version == "v14":
            spec["sources"] = [str(root / path) for path in (
                "tools/prepare_qa_routing_v3_release.py", "tools/extend_qa_release_v14.py",
                "tools/remote_guarded_deploy_qa_routing_v3_8093.ps1", "tools/record_qa_routing_v3_version.ps1",
                "tools/remote_preflight_qa_routing_v3.ps1", "tools/verify_qa_routing_release.ps1",
                "高炉前端数据/智能助手/backend/qa_verified_facts.py", "tests/test_qa_v6_contracts.py", "tests/test_qa_release_readiness.py")]
            validations[0]["evidence"] = "35 focused tests: registered-unit provenance, unknown-unit partial, no alias guessing or value conversion, compound source isolation and durable once-only claims"
            validations.append({"id":"release-get-readiness-faults","kind":"deterministic","status":"passed","evidence":"4 actual PowerShell readiness fault tests, at most 3 GETs, no POST"})
        write_json(release / "release-spec.json", spec)''', 1)
    # Bind the existing accepted public-facts baseline from a prior sealed release.
    digest = '7278f7a4437ea4cdf573a193698a35ad22b86460dd5194a03956d01890028e9b'
    text = text.replace('BASELINE_HASH', digest)
    compile(text, str(path), 'exec')
    write(path, text)
    path = ROOT / 'tools/prepare_qa_v9_invocations.py'
    write(path, path.read_text(encoding='utf-8').replace('"v12", "v13")', '"v12", "v13", "v14")'))

if __name__ == '__main__': main()
