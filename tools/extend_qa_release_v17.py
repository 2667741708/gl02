"""Prepare the single-module V17 release recipe; no remote operations."""
import json
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def replace_one(path, old, new):
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise ValueError('Reviewed release seam changed: ' + str(path))
    path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')


def extend_v18():
    """Reuse release registration for the exact two-target provenance update."""
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v18' in recipes:
        raise ValueError('V18 recipe already created; do not replay preparation')
    reads = dict(recipes['v17']['read_files'])
    reads.pop('高炉前端数据/智能助手/backend/ollama_proxy_server.py')
    reads.pop('高炉前端数据/智能助手/backend/mcp_conversation_context.py')
    reads['高炉前端数据/智能助手/backend/qa_history_compound.py'] = 'a7b1cd2cde3b9ce53df5e6611164e3330dae7af0c604e6f627a191072e99ab9a'
    recipes['v18'] = {
        'artifacts': {
            'ollama_proxy_server.py': {'baseline': ['3e535565e7579b4f33a29faf5938092d4b2b84708fa3dd410ff4ba8d4c6d50b6'],
                'markers': ['qa_context_state.persist_owned_context_binding', 'owner_subject, user_message_id'], 'allow_create': False},
            'mcp_conversation_context.py': {'baseline': ['e7f580c71eb334dde67343c5afc3a91e3e508408fd1a252f9e4a48f74f8d8507'],
                'markers': ['def load_owned_tool_context', 'def persist_owned_context_binding', 'def _owned_ancestry'], 'allow_create': False}},
        'read_files': reads,
        'sources': ['tools/qa_routing_release_extensions.json', 'tools/extend_qa_release_v17.py',
            'tools/build_qa_routing_v18_candidate.py', 'tools/prepare_qa_routing_v3_release.py',
            'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'tools/record_qa_routing_v3_version.ps1',
            'tools/remote_preflight_qa_routing_v3.ps1', 'tools/verify_qa_routing_release.ps1',
            '高炉前端数据/智能助手/backend/mcp_conversation_context.py',
            'tests/test_qa_context_provenance.py', 'tests/test_qa_context_provenance_seams.py'],
        'validations': [{'id':'focused-pytest','kind':'deterministic','status':'passed',
            'evidence':'104 focused tests including actual owner/role SQL, per-field message ancestry and actual accepted proxy persistence seams'},
            {'id':'remote-readonly-preflight','kind':'readonly_remote','status':'pending'}]}
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
                 'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1'):
        replace_one(ROOT / 'tools' / name, "'V16','V17')", "'V16','V17','V18')")
    replace_one(ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1',
        'if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V18') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $Allowed = @('高炉前端数据/智能助手/backend/ollama_proxy_server.py',\n"
        "        '高炉前端数据/智能助手/backend/mcp_conversation_context.py')\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT / 'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
        "if ($Version -eq 'V18') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v18-20260916-r1'\n"
        "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v18-20260916-r1'\n"
        "    $CommitMessage = 'fix: bind owner checked routing message ancestry [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v18-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
        "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
        "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT / 'tools/remote_preflight_qa_routing_v3.ps1',
        "if ($Version -eq 'V17') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v17-20260916-r1' }",
        "if ($Version -eq 'V17') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v17-20260916-r1' }\n"
        "if ($Version -eq 'V18') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v18-20260916-r1' }")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v16", "v17")', '"v16", "v17", "v18")')
    registry.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('V18 exact two-target recipe registered')


def extend_v19():
    """Register the production-adapter hotfix with the reviewed single target."""
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v19' in recipes:
        raise ValueError('V19 recipe already created; do not replay preparation')
    recipe = json.loads(json.dumps(recipes['v18']))
    recipe['artifacts'] = {'mcp_conversation_context.py': {
        'baseline':['d38baacb6b7ef1d52201222e987f19f8cd55e6eedd3c5e7631bbfb4f1ad59090'],
        'markers':['RETURNING id', 'rows = cursor.fetchall()', 'def _owned_ancestry'], 'allow_create':False}}
    recipe['read_files']['高炉前端数据/智能助手/backend/ollama_proxy_server.py'] = 'c8b2c1afebf921715d5b588540a0b727c69ce983ae0870dee2c3d5551a9711f0'
    recipe['sources'] = [name for name in recipe['sources'] if name != 'tools/build_qa_routing_v18_candidate.py']
    recipe['validations'] = [{'id':'focused-pytest','kind':'deterministic','status':'passed',
        'evidence':'107 distinct focused tests:106 combined plus1 actual production PgCompatConnection/CursorAdapter without rowcount;correct and unauthorized RETURNING paths checked'},
        {'id':'remote-readonly-preflight','kind':'readonly_remote','status':'pending'}]
    recipes['v19'] = recipe
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
                 'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1'):
        replace_one(ROOT / 'tools' / name, "'V17','V18')", "'V17','V18','V19')")
    replace_one(ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1', 'if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V19') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $Allowed = @('高炉前端数据/智能助手/backend/mcp_conversation_context.py')\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT / 'tools/record_qa_routing_v3_version.ps1', '$Operation = Get-Content',
        "if ($Version -eq 'V19') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v19-20260916-r1'\n"
        "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v19-20260916-r1'\n"
        "    $CommitMessage = 'fix: use adapter supported returned IDs for context binding [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v19-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
        "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
        "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT / 'tools/remote_preflight_qa_routing_v3.ps1',
        "if ($Version -eq 'V18') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v18-20260916-r1' }",
        "if ($Version -eq 'V18') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v18-20260916-r1' }\n"
        "if ($Version -eq 'V19') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v19-20260916-r1' }")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v17", "v18")', '"v17", "v18", "v19")')
    registry.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    candidate = ROOT / '.codex_runtime/qa-routing-v19/candidate'
    candidate.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ROOT / '高炉前端数据/智能助手/backend/mcp_conversation_context.py', candidate / 'mcp_conversation_context.py')
    print('V19 exact context-adapter hotfix registered')


def extend_v20():
    """Register the one-line planner repair against the accepted V19 release."""
    registry=ROOT/'tools/qa_routing_release_extensions.json'
    recipes=json.loads(registry.read_text(encoding='utf-8'))
    if 'v20' in recipes: raise ValueError('V20 recipe already created; no preparation replay')
    recipe=json.loads(json.dumps(recipes['v19']))
    recipe['artifacts']={'ollama_proxy_server.py':{'baseline':['c8b2c1afebf921715d5b588540a0b727c69ce983ae0870dee2c3d5551a9711f0'],
        'markers':['"它们", "该变量", "这个", "那个", "这些"','qa_context_state.persist_owned_context_binding'], 'allow_create':False}}
    recipe['read_files'].pop('高炉前端数据/智能助手/backend/ollama_proxy_server.py')
    recipe['read_files']['高炉前端数据/智能助手/backend/mcp_conversation_context.py']='98fb56b92135df039e22dd0eac812fda24071a07f188e997f7e5a1094158fbd5'
    recipe['sources'] += ['tools/build_qa_routing_v20_candidate.py','tests/test_qa_followup_planning.py']
    recipe['validations']=[{'id':'focused-pytest','kind':'deterministic','status':'passed',
        'evidence':'100 focused tests including12 actual accepted planner/sensor seams and referential/explicit-object counterexamples'},
        {'id':'remote-readonly-preflight','kind':'readonly_remote','status':'pending'}]
    recipes['v20']=recipe
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1','record_qa_routing_v3_version.ps1',
                 'remote_preflight_qa_routing_v3.ps1','verify_qa_routing_release.ps1'):
        replace_one(ROOT/'tools'/name,"'V18','V19')","'V18','V19','V20')")
    replace_one(ROOT/'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1','if ($StageRoot -ne $ExpectedStage)',
        "if ($Version -eq 'V20') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $Allowed = @('高炉前端数据/智能助手/backend/ollama_proxy_server.py')\n}\nif ($StageRoot -ne $ExpectedStage)")
    replace_one(ROOT/'tools/record_qa_routing_v3_version.ps1','$Operation = Get-Content',
        "if ($Version -eq 'V20') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
        "    $ExecutionId = 'qa-routing-v20-20260916-r1'\n"
        "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v20-20260916-r1'\n"
        "    $CommitMessage = 'fix: preserve server owned referential planning context [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v20-20260916-r1]'\n"
        "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
        "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
        "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    replace_one(ROOT/'tools/remote_preflight_qa_routing_v3.ps1',"if ($Version -eq 'V19') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v19-20260916-r1' }",
        "if ($Version -eq 'V19') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v19-20260916-r1' }\n"
        "if ($Version -eq 'V20') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v20-20260916-r1' }")
    replace_one(ROOT/'tools/prepare_qa_v9_invocations.py','"v18", "v19")','"v18", "v19", "v20")')
    replace_one(ROOT/'tools/stage_qa_release.py',"('v18', 'v19')","('v18', 'v19', 'v20')")
    registry.write_text(json.dumps(recipes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('V20 single proxy planner target registered')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('v17', 'v18', 'v19', 'v20'), default='v17')
    args = parser.parse_args()
    if args.version == 'v20':
        extend_v20()
        return
    if args.version == 'v19':
        extend_v19()
        return
    if args.version == 'v18':
        extend_v18()
        return
    registry = ROOT / 'tools/qa_routing_release_extensions.json'
    recipes = json.loads(registry.read_text(encoding='utf-8'))
    if 'v17' in recipes:
        raise ValueError('V17 recipe already created; do not replay preparation')
    reads = dict(recipes['v16']['read_files'])
    reads['高炉前端数据/智能助手/backend/ollama_proxy_server.py'] = '3e535565e7579b4f33a29faf5938092d4b2b84708fa3dd410ff4ba8d4c6d50b6'
    recipes['v17'] = {
        'artifacts': {'qa_history_compound.py': {
            'baseline': ['b363bd8e2d127cb74fb3d33120e7eb9acd1eb2c9f992d84244e26599ddd09687'],
            'markers': ['qa-history-compound-v2', 'def normalize_present', 'revalidated_latest_tool_payload'],
            'allow_create': False}},
        'read_files': reads,
        'sources': ['tools/qa_routing_release_extensions.json', 'tools/extend_qa_release_v17.py',
                    'tools/prepare_qa_routing_v3_release.py', 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1',
                    'tools/record_qa_routing_v3_version.ps1', 'tools/remote_preflight_qa_routing_v3.ps1',
                    'tools/verify_qa_routing_release.ps1', '高炉前端数据/智能助手/backend/qa_history_compound.py',
                    'tests/test_qa_history_completion.py', 'tests/test_qa_history_compound.py',
                    'tests/test_qa_history_compound_seams.py'],
        'validations': [{'id': 'focused-pytest', 'kind': 'deterministic', 'status': 'passed',
                         'evidence': '133 focused tests including 21 legacy-completion and typed latest-result counterexamples'},
                        {'id': 'remote-readonly-preflight', 'kind': 'readonly_remote', 'status': 'pending'}]}
    # Keep the reviewed historic V16 recipe intact; add an exact V17 allowlist.
    for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1',
                 'remote_preflight_qa_routing_v3.ps1', 'verify_qa_routing_release.ps1'):
        path = ROOT / 'tools' / name
        replace_one(path, "'V15','V16')", "'V15','V16','V17')")
    path = ROOT / 'tools/remote_guarded_deploy_qa_routing_v3_8093.ps1'
    replace_one(path, "if ($StageRoot -ne $ExpectedStage)",
                "if ($Version -eq 'V17') {\n    $Req = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
                "    $Allowed = @('高炉前端数据/智能助手/backend/qa_history_compound.py')\n}\n"
                "if ($StageRoot -ne $ExpectedStage)")
    path = ROOT / 'tools/record_qa_routing_v3_version.ps1'
    replace_one(path, '$Operation = Get-Content',
                "if ($Version -eq 'V17') {\n    $RequirementId = 'REQ-QA-FULL-ISSUE-INVENTORY-20260916'\n"
                "    $ExecutionId = 'qa-routing-v17-20260916-r1'\n"
                "    $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v17-20260916-r1'\n"
                "    $CommitMessage = 'fix: validate mixed history subtask completion [REQ-QA-FULL-ISSUE-INVENTORY-20260916] [qa-routing-v17-20260916-r1]'\n"
                "    $Guard = Join-Path $StageRoot 'git_record_guard.py'\n"
                "    $OperationPath = Join-Path $StageRoot 'operation.json'\n"
                "    $PlanPath = Join-Path $StageRoot 'record-plan.json'\n}\n$Operation = Get-Content")
    path = ROOT / 'tools/remote_preflight_qa_routing_v3.ps1'
    replace_one(path, "if ($Version -eq 'V16') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v16-20260916-r1' }",
                "if ($Version -eq 'V16') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v16-20260916-r1' }\n"
                "if ($Version -eq 'V17') { $StageRoot = 'C:/Users/Administrator/AppData/Local/Temp/qa-routing-v17-20260916-r1' }")
    replace_one(ROOT / 'tools/prepare_qa_v9_invocations.py', '"v15", "v16")', '"v15", "v16", "v17")')
    registry.write_text(json.dumps(recipes, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    candidate = ROOT / '.codex_runtime/qa-routing-v17/candidate'
    candidate.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ROOT / '高炉前端数据/智能助手/backend/qa_history_compound.py', candidate / 'qa_history_compound.py')
    print(json.dumps({'ok': True, 'version': 'v17', 'target_count': 1}))


if __name__ == '__main__': main()
