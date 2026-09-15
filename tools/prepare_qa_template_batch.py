"""Create a private, oracle-free execution plan from a reviewed template inventory."""
import argparse
import hashlib
import json
from pathlib import Path

def build(inventory,collector,hashes):
    ready=[r for r in inventory['rows'] if r['source_status']=='ready']
    # Preserve source/turn order within each category; knowledge suite runs last.
    ready.sort(key=lambda r:r.get('category')=='knowledge')
    keys=('case_id','prompt','prompt_mode','conversation_group','turn_index')
    return dict(schema='bf.qa.template-batch.v1',phase='templates-v2',
        collector_sha256=hashlib.sha256(collector).hexdigest(),runtime_hashes=hashes,
        cases=[{k:r[k] for k in keys if k in r} for r in ready])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--collector',type=Path,required=True)
    p.add_argument('--runtime-state',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    plan=build(json.loads(a.inventory.read_text(encoding='utf-8')),a.collector.read_bytes(),
        json.loads(a.runtime_state.read_text(encoding='utf-8')))
    a.output.write_bytes((json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'case_count':len(plan['cases']),'plan_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),
        'expected_answers_in_payload':False}))
if __name__=='__main__': main()
