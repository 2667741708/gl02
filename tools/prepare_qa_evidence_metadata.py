"""Prepare non-secret deployment metadata, after local validation."""
import ast, hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/".codex_runtime/qa-release"
C=D/"candidate"
STAGE="C:/Users/Administrator/AppData/Local/Temp/qa-evidence-20260915-v2"
PROD="F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
REL="高炉前端数据/智能助手/backend/"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_bytes((json.dumps(x,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
scope=json.loads((D/"scope.json").read_text(encoding="utf-8"))
targets={REL+n:{"candidate_path":STAGE+"/"+n,"sha256":sha(C/n)} for n in ("ollama_proxy_server.py","qa_evidence_policy.py")}
save(D/"recordability-expectation.json",dict(schema="bf.deploy.git-recordability-expectation.v1",repo=PROD,expected_head=scope["base_head"],concurrency_mode="path-scoped",read_set=scope["read_set"],targets=targets))
read_hashes=["50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033","0853b77655247030436f0a55a9c973503dc6a853280f3f9aa09d28be6cbeb901","149340c3ffbbdac28a6db7d917102ffe1681a15ac557bea96077887d7b2c15c0"]
save(D/"scope-gate.json",dict(head=scope["base_head"],read_files=[dict(path=p,sha256=h) for p,h in zip(scope["read_set"],read_hashes)]))
# Every function/method not in the explicit edit scope must retain the same AST.
def definitions(source):
    result={}
    def walk(nodes,prefix=""):
        for n in nodes:
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                name=prefix+n.name
                if not isinstance(n,ast.ClassDef):result[name]=ast.dump(n,include_attributes=False)
                else:walk(n.body,name+".")
    walk(ast.parse(source).body)
    return result
before=definitions((D/"baseline/ollama_proxy_server.py").read_text(encoding="utf-8"))
after=definitions((C/"ollama_proxy_server.py").read_text(encoding="utf-8"))
allowed={"qa_grounded_mcp_analysis","qa_mcp_sensor_query_plan","deterministic_mcp_answer","qa_mcp_final_fallback"}
changed={n for n in before if before[n]!=after.get(n)}
assert changed<=allowed, changed-allowed
markers=["qa_request_control.install(Handler, globals())","diagnosis_ai_analysis_api.install_handler(Handler, globals())","/api/auth/register","/api/qa/asr/status","/api/qa/asr/session","validated_abc_initial_answer_with_repair","owner_subject","cache_abc_rule_analysis","cross_source_with_analysis"]
text=(C/"ollama_proxy_server.py").read_text(encoding="utf-8")
assert all(m in text for m in markers)
save(ROOT/"tests/qa_shared_feature_contract.v1.json",dict(schema="bf.deploy.shared-feature-contract.v1",contract_id="qa-shared-proxy-20260915-v1",features={"accepted_proxy_features":{"artifacts":{"proxy":markers}}}))
save(D/"ast-preservation.json",dict(passed=True,unchanged_definition_count=len(before)-len(changed),changed_definitions=sorted(changed),new_definitions=sorted(set(after)-set(before)),candidate_sha256=sha(C/"ollama_proxy_server.py")))
print(json.dumps({"targets":targets,"changed_definitions":sorted(changed),"unchanged_definition_count":len(before)-len(changed)},ensure_ascii=False))
