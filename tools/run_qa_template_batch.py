"""Run an authorized version-pinned QA batch serially with durable no-replay claims."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,obj):
    tmp=path.with_suffix('.tmp')
    tmp.write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    tmp.replace(path)

def verify(plan,root,collector):
    if digest(collector)!=plan['collector_sha256']: raise RuntimeError('collector hash changed')
    if plan.get('catalog_sha256') and digest(root/'数据库同步和存取/config/点位语义目录.json')!=plan['catalog_sha256']:
        raise RuntimeError('catalog hash changed')
    for relative,sha in plan['runtime_hashes'].items():
        if digest(root/relative)!=sha: raise RuntimeError('runtime version changed: '+relative)
    if plan.get('model_identity'):
        identity=plan['model_identity']
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=6) as response:
            tags=json.load(response)
        matches=[row for row in tags.get('models',[]) if row.get('name')==identity['name']]
        approved=identity.get('approved_digests') or [identity['digest']]
        if len(matches)!=1 or matches[0].get('digest') not in approved:
            raise RuntimeError('model identity changed; no next request sent')
        with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=6) as response:
            resident=json.load(response).get('models',[])
        if len(resident)!=1 or resident[0].get('digest')!=matches[0].get('digest'):
            raise RuntimeError('resident model differs from frozen identity; no next request sent')
        return {'name':identity['name'],'digest':matches[0]['digest']}
    return None

def model_ready():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8093/api/ollama/status',timeout=10) as r:
            data=json.load(r)
        return all(data.get(k) for k in ('ok','proxy_ok','ollama_ok','model_ok'))
    except Exception: return False

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--collector',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--detach',action='store_true')
    a=p.parse_args()
    if not a.execute: p.error('--execute required')
    plan=read(a.plan)
    if len({c['case_id'] for c in plan['cases']})!=len(plan['cases']): raise RuntimeError('duplicate case ID')
    a.output.mkdir(parents=True,exist_ok=True)
    if a.detach:
        with (a.output/'launch.claim').open('x',encoding='utf-8') as claim:
            claim.write(json.dumps({'plan_sha256':digest(a.plan),'created_at':time.time()}))
        with (a.output/'batch.stdout').open('xb') as out, (a.output/'batch.stderr').open('xb') as err:
            child=subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve()),
                '--root',str(a.root),'--plan',str(a.plan),'--collector',str(a.collector),
                '--output',str(a.output),'--execute'],stdout=out,stderr=err,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        print(json.dumps({'started':True,'pid':child.pid,'case_count':len(plan['cases']),
            'output':str(a.output),'automatic_replay':False})); return
    state={'schema':'bf.qa.batch-progress.v1','pid':os.getpid(),'plan_sha256':digest(a.plan),
        'total':len(plan['cases']),'completed':0,'requests':0,'state':'running','results':[],
        'automatic_retries':0,'started_at':time.time()}
    conversations=dict(plan.get('initial_conversations') or {})
    progress=a.output/'progress.json'
    try:
        verify(plan,a.root,a.collector)
        for case in plan['cases']:
            state['active_case']=case['case_id']; write(progress,state)
            before_identity=verify(plan,a.root,a.collector)
            caseid=case['case_id']; outfile=a.output/(caseid+'.json'); claim=a.output/(caseid+'.claim')
            if outfile.exists() or claim.exists():
                raise RuntimeError('existing evidence requires explicit read-only recovery: '+caseid)
            for _ in range(20):
                if model_ready(): break
                state['state']='waiting_for_model'; write(progress,state); time.sleep(30)
            else: raise RuntimeError('model unavailable; no case request sent')
            # The readiness wait may outlive an alias/model switch; recheck before claiming/sending.
            before_identity=verify(plan,a.root,a.collector)
            state['state']='running'; write(progress,state)
            group=case.get('conversation_group')
            if group and case.get('turn_index',0)>0 and group not in conversations:
                raise RuntimeError('prior turn unavailable: '+caseid)
            with claim.open('x',encoding='utf-8') as f:
                json.dump({'case_id':caseid,'prompt_sha256':hashlib.sha256(case['prompt'].encode()).hexdigest(),
                    'request_may_be_sent':True,'created_at':time.time(),'before_identity':before_identity},f)
            # Only actual user inputs reach the collector, never test oracles.
            payload={k:case[k] for k in ('case_id','prompt','prompt_mode') if k in case}
            cmd=[sys.executable,'-X','utf8',str(a.collector),'--root',str(a.root),
                '--case-json',json.dumps(payload,ensure_ascii=False),'--phase',plan['phase'],'--timeout','180','--execute']
            if group and group in conversations: cmd+=['--conversation-id',conversations[group]]
            with outfile.open('xb') as output, (a.output/(caseid+'.err')).open('xb') as errors:
                process=subprocess.run(cmd,stdout=output,stderr=errors,timeout=220)
            if process.returncode: raise RuntimeError('collector failed; do not replay: '+caseid)
            result=read(outfile)
            state['requests']+=result.get('request_count',0)
            if result.get('transport_error') or not result.get('terminated'):
                raise RuntimeError('uncertain request; do not replay: '+caseid)
            if group: conversations[group]=result['conversation_id']
            state['completed']+=1
            state['results'].append({'case_id':caseid,'seconds':result.get('elapsed_seconds'),
                'has_answer':bool(result.get('answer')),'error_code':result.get('error_code'),
                'route':result.get('final',{}).get('answer_route'),
                'tool_calls':len(result.get('tool_starts',[])),
                'answer_contract':'pending_review' if result.get('answer') else 'failed',
                'before_identity':before_identity})
            write(progress,state)
            # Keep already-sent evidence even if model/code drift occurred during the turn.
            try:
                after_identity=verify(plan,a.root,a.collector)
                state['results'][-1]['after_identity']=after_identity
                if after_identity!=before_identity:
                    raise RuntimeError('model digest changed during turn')
                state['results'][-1]['post_turn_identity']='matched'
            except Exception:
                state['results'][-1]['post_turn_identity']='drift_or_unavailable'
                write(progress,state)
                raise RuntimeError('identity drift after sent case; evidence retained; do not replay: '+caseid)
        state['state']='completed'; state['active_case']=None
    except Exception as exc:
        state['state']='blocked'; state['error_type']=type(exc).__name__; state['reason']=str(exc)
    finally:
        state['updated_at']=time.time(); write(progress,state)
    print(json.dumps({k:v for k,v in state.items() if k!='results'},ensure_ascii=False))

if __name__=='__main__': main()

