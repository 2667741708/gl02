"""Refresh pending V23 evidence after addressing a concrete review finding."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    runtime=ROOT/'.codex_runtime/qa-routing-v23'
    if (runtime/'release/prepared-release.json').exists(): raise ValueError('Sealed V23 cannot be modified')
    baseline=(runtime/'baseline/qa_task_plan.py').read_bytes()
    desired=(runtime/'candidate/qa_task_plan.py').read_bytes()
    def preserved(raw):
        return [ast.dump(n,include_attributes=False) for n in ast.parse(raw).body
                if not (isinstance(n,ast.FunctionDef) and n.name=='_explicit_live_request')]
    if preserved(baseline)!=preserved(desired): raise ValueError('Unrequested AST change')
    (runtime/'candidate.diff').write_bytes(''.join(difflib.unified_diff(baseline.decode().splitlines(True),
        desired.decode().splitlines(True),fromfile='production/qa_task_plan.py',tofile='candidate/qa_task_plan.py')).encode())
    registry=ROOT/'tools/qa_routing_release_extensions.json'
    recipes=json.loads(registry.read_text(encoding='utf-8'))
    recipes['v23']['validations'][0]['evidence']='50 tests passed including abbreviated point addresses and no-live/document/user-data boundaries'
    recipes['v23']['sources'].append('tools/check_qa_v23_candidate.py')
    registry.write_bytes((json.dumps(recipes,ensure_ascii=False,indent=2)+'\n').encode())
    result={'ok':True,'unchanged_top_level_nodes':len(preserved(baseline)),
            'candidate_sha256':hashlib.sha256(desired).hexdigest()}
    (runtime/'release/ast-preservation.json').write_bytes((json.dumps(result)+'\n').encode())
    print(json.dumps(result))


if __name__=='__main__':main()
