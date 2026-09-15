"""Exclude every claimed row after read-only recovery; never replay interrupted rows."""
import argparse
import hashlib
import json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--plan',type=Path,required=True)
p.add_argument('--claimed',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args(); plan=json.loads(a.plan.read_text(encoding='utf-8')); recovery=json.loads(a.claimed.read_text(encoding='utf-8'))
if not recovery.get('previous_processes_absent') or recovery.get('automatic_replay') is not False:
    raise SystemExit('read-only recovery evidence required')
claimed=set(recovery['claimed_case_ids'])
if not claimed <= {c['case_id'] for c in plan['cases']}: raise SystemExit('unknown claimed case')
groups={c.get('conversation_group') for c in plan['cases'] if c['case_id'] in claimed and c.get('conversation_group')}
if groups: raise SystemExit('multi-turn continuation requires recovered conversation IDs')
plan['predecessor_plan_sha256']=hashlib.sha256(a.plan.read_bytes()).hexdigest()
plan['excluded_claimed_case_ids']=sorted(claimed)
plan['cases']=[c for c in plan['cases'] if c['case_id'] not in claimed]
a.output.write_bytes((json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
print(json.dumps({'remaining':len(plan['cases']),'excluded':len(claimed),'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}))
