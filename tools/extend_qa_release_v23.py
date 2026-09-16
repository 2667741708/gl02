"""Register the minimal single-window intent repair after V22 real failures."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

from extend_qa_release_v17 import replace_one

ROOT = Path(__file__).resolve().parents[1]
REL = '高炉前端数据/智能助手/backend/qa_task_plan.py'


def main():
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v23' in recipes: raise ValueError('V23 already registered')
    runtime = ROOT / '.codex_runtime/qa-routing-v23'
    baseline = (runtime / 'baseline/qa_task_plan.py').read_bytes()
    expected = '8b9fa2eec70c9fc6ce5d33e2ff1613231ef83072595fd99a94f1e1c700fc1fb1'
    if hashlib.sha256(baseline).hexdigest() != expected: raise ValueError('Production baseline mismatch')
    desired = (ROOT / REL).read_bytes()
    def preserved(raw):
        return [ast.dump(node, include_attributes=False) for node in ast.parse(raw).body
                if not (isinstance(node, ast.FunctionDef) and node.name == '_explicit_live_request')]
    if preserved(baseline) != preserved(desired): raise ValueError('Unrequested planner AST change')
    candidate = runtime / 'candidate'
    candidate.mkdir(exist_ok=False)
    (candidate / 'qa_task_plan.py').write_bytes(desired)
    (runtime / 'candidate.diff').write_bytes(''.join(difflib.unified_diff(
        baseline.decode().splitlines(True), desired.decode().splitlines(True),
        fromfile='production/qa_task_plan.py', tofile='candidate/qa_task_plan.py')).encode())
    reads = dict(recipes['v22']['read_files'])
    reads.pop(REL)
    reads.update({
        '高炉前端数据/智能助手/backend/ollama_proxy_server.py':'c90f82cf2466bf4004efed330d21a252fdd8c847605f966909102a9c7653aefc',
        '高炉前端数据/智能助手/backend/qa_verified_facts.py':'51112c7f8b7de36dab6ce49046968921ce3194adc1348005f4a8c09d73dbcde6',
        '高炉前端数据/智能助手/backend/qa_evidence_policy.py':'d4e44deda3df4740620a9baa6c880023f28fe8683b228015c519ae240c3d769d',
    })
    scripts = ['remote_guarded_deploy_qa_routing_v3_8093.ps1','record_qa_routing_v3_version.ps1',
               'remote_preflight_qa_routing_v3.ps1','verify_qa_routing_release.ps1']
    recipes['v23'] = {'artifacts': {'qa_task_plan.py': {'baseline':[expected],
        'markers':['REQ-QA-SINGLE-WINDOW-OBSERVATION-20260917','def tool_allowed'], 'allow_create':False}},
        'read_files':reads, 'sources':['tools/extend_qa_release_v23.py','tools/qa_routing_release_extensions.json',
        'tools/prepare_qa_routing_v3_release.py',*['tools/'+n for n in scripts],REL,'tests/test_qa_single_window_routing.py'],
        'validations':[{'id':'focused-pytest','kind':'deterministic','status':'passed','evidence':'50 tests; single-window positives including abbreviated body-point addresses, no-live, user data, quoted/general/document boundaries'},
                       {'id':'remote-readonly-preflight','kind':'readonly_remote','status':'pending'}]}
    for name in scripts:
        replace_one(ROOT/'tools'/name, "'V21','V22')", "'V21','V22','V23')")
    replace_one(ROOT/'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1','if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V23') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n    $Allowed = @('"+REL+"')\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT/'tools/record_qa_routing_v3_version.ps1','$Operation = Get-Content',
        "if ($Version -eq 'V23') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v23-20260916-r1'\n    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v23-20260916-r1'\n"
        "    $CommitMessage = 'fix: route single-window observations to read-only data [REQ-QA-SINGLE-WINDOW-OBSERVATION-20260917] [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v23-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n    $OperationPath = Join-Path $StageRoot 'operation.json'\n    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT/'tools/remote_preflight_qa_routing_v3.ps1',"$Python = 'C:\\Program Files\\Python311\\python.exe'",
        "if ($Version -eq 'V23') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v23-20260916-r1' }\n$Python = 'C:\\Program Files\\Python311\\python.exe'")
    replace_one(ROOT/'tools/prepare_qa_v9_invocations.py','"v21", "v22")','"v21", "v22", "v23")')
    replace_one(ROOT/'tools/stage_qa_release.py',"'v21', 'v22')","'v21', 'v22', 'v23')")
    replace_one(ROOT/'tools/record_qa_release_preflight.py',"('v21','v22')","('v21','v22','v23')")
    registry.write_bytes((json.dumps(recipes,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok':True,'targets':[REL],'read_count':len(reads)}))


if __name__ == '__main__': main()
