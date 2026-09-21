"""Summarize collected QA evidence without treating nonempty answers as passes."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

def summarize(rows, inventory):
    by_id = {r['case_id']: r for r in inventory['rows']}
    ordered = sorted(float(r['seconds']) for r in rows)
    code_rows = [r for r in rows if r.get('answer', '').startswith('当前暂不提供代码')]
    arrows = [r for r in rows if r['question'].startswith('→')]
    return {
        'schema': 'bf.qa.collected-review.v1',
        'evaluation_id': 'Q-QA-ROUTING-RESULT-REVIEW-20260915',
        'scope': 'collected runtime metadata; answer fidelity requires case review',
        'collected_count': len(rows),
        'nonempty_answers': sum(bool(r.get('answer')) for r in rows),
        'answer_accuracy': None,
        'route_counts': dict(Counter(r.get('route') or 'no_final_route' for r in rows)),
        'latency_seconds': {'p50': ordered[len(ordered)//2],
                            'p95_nearest_rank': ordered[(math.ceil(.95*len(ordered)))-1],
                            'max': ordered[-1]},
        'no_code_response_count': len(code_rows),
        'no_code_non_arrow_count': sum(not r['question'].startswith('→') for r in code_rows),
        'no_code_case_ids': [r['case_id'] for r in code_rows],
        'known_structure_lines_executed': [r['case_id'] for r in arrows],
        'source_counts': dict(Counter(by_id[r['case_id']]['source_path'] for r in rows)),
        'knowledge_questions_collected': sum(by_id[r['case_id']].get('category') == 'knowledge' for r in rows),
        'observed_tool_error_counts': dict(Counter(t['error'] for r in rows for t in r['tools'] if t.get('error'))),
        'case_routes': [{k:r[k] for k in ('case_id','route','seconds','tool_calls')} for r in rows],
        'unmeasured': ['full-corpus answer accuracy','pass^5','six-user concurrency',
                      'guest/operator parity','all numerical claims','raw-series independent statistics']
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    raw=a.results.read_bytes()
    report=summarize(json.loads(raw),json.loads(a.inventory.read_text(encoding='utf-8')))
    report['private_input_sha256']=hashlib.sha256(raw).hexdigest()
    a.output.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({k:v for k,v in report.items() if k not in ('case_routes','no_code_case_ids','known_structure_lines_executed')},ensure_ascii=False))
if __name__=='__main__': main()

