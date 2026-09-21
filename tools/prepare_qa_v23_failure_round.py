"""Freeze V23 retests of confirmed originals and two newly reproduced failures."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    source=ROOT/'.codex_runtime/qa-routing-v22/templates.strata.plan.private.json'
    plan=json.loads(source.read_text(encoding='utf-8'))
    snapshot=json.loads((ROOT/'.codex_runtime/qa-routing-v23/release/post-record-snapshot.json').read_text(encoding='utf-8'))
    if not snapshot['ok']:raise ValueError('Production snapshot unhealthy')
    failures={'TPL-FACD6F5FE05C74FC','TPL-01EEE414179DB624'}
    plan['cases']=[row for row in plan['cases'] if row.get('cohort')=='first_collection_failed' or row['case_id'] in failures]
    if len(plan['cases'])!=407:raise ValueError('Failure cohort changed')
    plan.update(phase='after-v23',round='paired-v23-20260917-r1',production_commit=snapshot['head'],
                runtime_hashes=snapshot['runtime_hashes'],catalog_sha256=snapshot['catalog_sha256'],
                original_first_eight=0,v23_preceding_version_confirmed_failed=2)
    plan.pop('recovery',None)
    plan['policy']='Explicit new deployed version comparison; 405 originals plus two V22 failures; one POST per case; no automatic replay or unknown original'
    runtime=ROOT/'.codex_runtime/qa-routing-v23'
    output=runtime/'failure-round.plan.private.json'
    if output.exists():raise ValueError('Frozen V23 round exists; do not replay')
    output.write_bytes((json.dumps(plan,ensure_ascii=False,indent=2)+'\n').encode())
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest().upper()
    stage='C:/Users/Administrator/AppData/Local/Temp/qa-paired-v23-20260917-r1'
    files=[{'local':str(output),'remote':stage+'/templates.remaining.plan.json'}]
    for name,remote in [('run_qa_template_batch.py','batch.py'),('run_qa_live_case.py','collector.py'),('start_qa_batch_independent.ps1','start_qa_batch_independent.ps1')]:
        files.append({'local':str(ROOT/'tools'/name),'remote':stage+'/'+remote})
    manifest={'stage':stage,'total':len(plan['cases']),'plan_sha256':sha(output),'files':files}
    (runtime/'release/online-upload.private.json').write_bytes((json.dumps(manifest,indent=2)+'\n').encode())
    template=(ROOT/'.codex_runtime/qa-routing-v22/release/invoke-strata-online-round.ps1').read_text(encoding='utf-8')
    template=template.replace('qa-paired-v22-20260917-r2','qa-paired-v23-20260917-r1').replace('qa_paired_v22_20260917_r2','qa_paired_v23_20260917_r1')
    for prefix,new in [('$PlanHash =',sha(output)),('$BatchHash =',sha(ROOT/'tools/run_qa_template_batch.py'))]:
        old=next(line.split("'")[1] for line in template.splitlines() if line.startswith(prefix))
        template=template.replace(old,new)
    (runtime/'release/invoke-online-round.ps1').write_bytes(template.encode())
    print(json.dumps({'ok':True,'total':407,'initial_confirmed_failed':405,'v22_failed':2,'plan_sha256':sha(output)}))


if __name__=='__main__':main()
