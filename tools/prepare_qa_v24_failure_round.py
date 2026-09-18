"""Freeze a new version-pinned original-failure round, without sending requests."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v24'
    release = runtime / 'release'
    output = runtime / 'failure-round.plan.private.json'
    manifest_path = release / 'online-upload.private.json'
    if output.exists() or manifest_path.exists():
        raise ValueError('Frozen round exists; inspect instead of replaying')
    plan = json.loads((ROOT / '.codex_runtime/qa-routing-v23/failure-round.plan.private.json').read_text(encoding='utf-8'))
    snapshot = json.loads((release / 'post-record-snapshot.json').read_text(encoding='utf-8'))
    if not snapshot['ok'] or snapshot['head'] != 'b55f754ac8d8592e2819083f01a71438bd6e23c7':
        raise ValueError('Unverified V24 production snapshot')
    priority = ['TPL-BE97AA4EAD567003', 'TPL-A60B0CD794D49E48', 'TPL-C5DF79304112ED85']
    by_id = {row['case_id']: row for row in plan['cases']}
    if len(by_id) != 407 or len(plan['cases']) != 407:
        raise ValueError('Original failed-cohort round changed')
    plan['cases'] = [by_id[key] for key in priority] + [row for row in plan['cases'] if row['case_id'] not in priority]
    plan.update(phase='after-v24', round='paired-v24-20260917-r1', production_commit=snapshot['head'],
        runtime_hashes=snapshot['runtime_hashes'], catalog_sha256=snapshot['catalog_sha256'],
        model_identity=snapshot['model_identity'], collector_sha256=hashlib.sha256((ROOT / 'tools/run_qa_live_case.py').read_bytes()).hexdigest(),
        policy='New explicitly authorized V24 comparison after deployed changes; original questions unchanged; one POST per case; no automatic replay; do not combine V23/V24 accuracy denominators')
    output.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    stage = 'C:/Users/Administrator/AppData/Local/Temp/qa-paired-v24-20260917-r1'
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest().upper()
    template = (ROOT / '.codex_runtime/qa-routing-v23/release/invoke-r2-online-round.ps1').read_text(encoding='utf-8')
    substitutions = {
        'qa-paired-v23-20260917-r2': 'qa-paired-v24-20260917-r1',
        'qa_paired_v23_20260917_r2': 'qa_paired_v24_20260917_r1',
        '952F22764C8658B45904EF9EED0DD28DA33669906B5E2F96FC9A432E48046FAB': sha(output),
    }
    for old, new in substitutions.items():
        if template.count(old) != 1:
            raise ValueError('Reviewed launch binding changed')
        template = template.replace(old, new)
    batch = ROOT / 'tools/run_qa_template_batch.py'
    starter = ROOT / 'tools/start_qa_batch_independent.ps1'
    if sha(batch) != 'CB41506E30253D192204FED77F94903D2C771FB820939E122FF1CA0760DEABF7' or sha(starter) != '80849AF1C05240A9EB7A0441B28AE2261D33DF9CDEF5A41BF534DC037AD23DF3':
        raise ValueError('Previously reviewed execution tools changed')
    (release / 'invoke-online-round.ps1').write_bytes(template.encode('utf-8'))
    manifest = {'stage': stage, 'total': 407, 'plan_sha256': sha(output), 'files': [
        {'local': str(output), 'remote': stage + '/templates.remaining.plan.json'},
        {'local': str(batch), 'remote': stage + '/batch.py'},
        {'local': str(ROOT / 'tools/run_qa_live_case.py'), 'remote': stage + '/collector.py'},
        {'local': str(starter), 'remote': stage + '/start_qa_batch_independent.ps1'},
    ]}
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'version': 'v24', 'total': 407, 'priority': priority, 'automatic_replay': False}))


if __name__ == '__main__':
    main()
