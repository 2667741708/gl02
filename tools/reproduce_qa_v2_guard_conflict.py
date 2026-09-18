"""Read-only reproduction of the installed V2 answer-guard conflict."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

def module(path,name,expected):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('Source hash differs from audited V2: '+name)
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    sys.modules[name]=result
    spec.loader.exec_module(result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--policy',type=Path,required=True)
    a=p.parse_args()
    s=module(a.selection,'audit_selection','50eded25f48e7bedde8953e5120e406daaf6682acff2399e93bcb7864e684033')
    q=module(a.policy,'audit_policy','442ea9df0f2ab41738b8b9613491dcc4838890800974f96c3d8ccf27a2369d4d')
    facts=s.deterministic_evidence_summary([{'tool':'get_latest_gl02_value','result_text':json.dumps({'ok':True,'latest':{'value':42.5,'ts':'2026-09-15T12:00:00'}})}])
    result={
        'code_request_detected_for_normal_question':q.code_requested('俩铁口温度。'),
        'safe_facts_replaced_by_no_code':q.enforce_no_code(facts)==q.NO_CODE,
        'rounded_value_rejected':not s.answer_is_grounded('温度为42.5','温度实测42.500123'),
        'wrong_object_same_number_accepted':s.answer_is_grounded('顶压为42.5','温度为42.5'),
        'meaning':'reproduced defects; not acceptance passes'
    }
    if result != {
        'code_request_detected_for_normal_question':False,
        'safe_facts_replaced_by_no_code':True,
        'rounded_value_rejected':True,
        'wrong_object_same_number_accepted':True,
        'meaning':'reproduced defects; not acceptance passes'
    }: raise RuntimeError('Audited behavior changed')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__': main()

