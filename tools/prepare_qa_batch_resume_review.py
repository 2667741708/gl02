"""Resume only proven-unsent QA inputs, with full-catalog classification."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from import_qa_prompt_sources import disposition

PROVEN_UNSENT = 'TPL-C0EDCD587C852263'

def mode_for(prompt, ids):
    return 'structured' if any(re.search(r'(?<![A-Za-z0-9_])'+re.escape(v)+r'(?![A-Za-z0-9_])',prompt)
        for v in ids if re.search(r'[A-Za-z_]',v)) or re.search(r'\b[A-Za-z]+_[A-Za-z0-9_]+\b',prompt) else 'spoken'

def build(plan, inventory, recovery):
    if any(b['alive'] for b in recovery['batches']) or recovery['collectors']:
        raise ValueError('prior process still active')
    claims={c['case_id']:c for b in recovery['batches'] for c in b['claims']}
    index={r['case_id']:r for r in inventory['rows']}
    if not set(claims)<=set(index): raise ValueError('unknown claim')
    eligible_unsent=set()
    for cid,c in claims.items():
        if cid==PROVEN_UNSENT and 'line 74, in run' in (c.get('error_tail') or '') and 'oracle_invalid: internal catalog ID in prompt' in c['error_tail'] and c['state']=='unknown':
            eligible_unsent.add(cid)
    initial={}; blocked_groups=set()
    for c in plan['cases']:
        claim=claims.get(c['case_id']);group=c.get('conversation_group')
        if claim and group and c['case_id'] not in eligible_unsent:
            if claim['state']=='completed' and claim.get('conversation_id'): initial[group]=claim['conversation_id']
            else: blocked_groups.add(group)
    candidates=[]; audit=[]
    for c in plan['cases']:
        cid=c['case_id'];row=index[cid]
        status,reason=disposition(c['prompt'],row['kind'])
        mode=mode_for(c['prompt'],recovery['object_ids'])
        action='execute'
        if cid in claims and cid not in eligible_unsent: action='retain_prior_result'
        elif status!='ready': action='contract_only_or_skip'
        elif c.get('conversation_group') in blocked_groups: action='blocked_dependency'
        if action=='execute': candidates.append(dict(c,prompt_mode=mode))
        audit.append({'case_id':cid,'action':action,'reason':reason,'original_mode':c.get('prompt_mode'),
                      'reviewed_mode':mode,'reviewed_status':status,'previously_claimed':cid in claims,
                      'proven_not_sent':cid in eligible_unsent,'source_path':row['source_path'],'source_line':row['source_line']})
    result=dict(plan,cases=candidates,initial_conversations=initial,catalog_sha256=recovery['catalog_sha256'],
                predecessor_claimed_ids=sorted(claims),proven_not_sent_ids=sorted(eligible_unsent))
    return result, {'schema':'bf.qa.resume-review.v1','requirement_id':'REQ-QA-COMPLETE-COLLECTION-BEFORE-ROUTING-20260915',
        'counts':dict(Counter(x['action'] for x in audit)),'mode_corrections':sum(x['original_mode']!=x['reviewed_mode'] for x in audit),
        'automatic_replay':False,'reviewed_rows':audit}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','inventory','recovery','output','audit'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    plan,audit=build(json.loads(a.plan.read_text(encoding='utf-8')),json.loads(a.inventory.read_text(encoding='utf-8')),
                     json.loads(a.recovery.read_text(encoding='utf-8')))
    plan['predecessor_plan_sha256']=hashlib.sha256(a.plan.read_bytes()).hexdigest()
    for path,obj in ((a.output,plan),(a.audit,audit)):path.write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'remaining':len(plan['cases']),'counts':audit['counts'],'mode_corrections':audit['mode_corrections'],
                     'plan_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest()}))
if __name__=='__main__':main()

