"""Check inventory integrity and non-chat template contracts without model calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); inv=json.loads(a.inventory.read_text(encoding='utf-8'))
    result=dict(schema='bf.qa.template-contracts.v1',model_requests=0,source_checks=[],row_checks=[])
    for s in inv['sources']:
        path=a.source_root/s['path']
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        result['source_checks'].append(dict(path=s['path'],status='passed' if actual and actual==s.get('sha256') else 'missing_or_changed'))
    ids={r['case_id'] for r in inv['rows']}
    for row in inv['rows']:
        status=row['source_status']; check='not_applicable'; details=[]
        if status=='duplicate': check='passed' if row.get('duplicate_of') in ids else 'failed'
        elif status=='skipped': check='passed' if row.get('skip_reason') else 'failed'
        elif status=='fixture_only': check='requires_isolated_fault_execution'
        elif status=='contract_only':
            raw=row['source_text'].strip()
            if row['kind']=='system_template':
                check='source_recorded_runtime_binding_review_required'
            elif raw.startswith(('{','[')):
                try: json.loads(raw); check='json_syntax_passed'
                except json.JSONDecodeError: check='snippet_not_standalone_json'
            else: check='source_recorded_not_a_chat_case'
        else: check='live_execution_required'
        result['row_checks'].append(dict(case_id=row['case_id'],status=check))
    result['counts']=dict(Counter(r['status'] for r in result['row_checks']))
    a.output.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'counts':result['counts'],'source_failures':[s for s in result['source_checks'] if s['status']!='passed']},ensure_ascii=False))
if __name__=='__main__': main()
