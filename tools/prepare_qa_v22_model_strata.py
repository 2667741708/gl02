"""Prepare a proven-unsent recovery, retaining per-turn approved model strata."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.codex_runtime/qa-routing-v22'


def main():
    recovery = json.loads((RUNTIME / 'release/r1-readonly-recovery.json').read_text(encoding='utf-8'))
    if recovery['process_present'] or recovery['output_exists'] or recovery['claimed_case_ids']:
        raise ValueError('Recovery does not prove all cases unsent')
    original = RUNTIME / 'templates.remaining.plan.private.json'
    plan = json.loads(original.read_text(encoding='utf-8'))
    plan['model_identity']['approved_digests'] = [
        '9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb',
        'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124']
    plan['round'] = 'paired-v22-20260917-r2'
    plan['recovery'] = {'prior_plan_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
                        'prior_round': 'paired-v22-20260917-r1', 'prior_claimed_case_ids': [],
                        'all_proven_unsent': True}
    plan['comparison_scope'] = 'Current production system; per-turn start/end model digest samples; model-stratified observations, not fixed-weight causality'
    output = RUNTIME / 'templates.strata.plan.private.json'
    if output.exists(): raise ValueError('Frozen recovery already exists; do not replay')
    output.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
    manifest = json.loads((RUNTIME / 'release/online-upload.private.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        row['remote'] = row['remote'].replace('qa-paired-v22-20260917-r1', 'qa-paired-v22-20260917-r2')
        if row['remote'].endswith('/templates.remaining.plan.json'): row['local'] = str(output)
    manifest['stage'] = manifest['stage'].replace('-r1', '-r2')
    manifest['plan_sha256'] = sha(output)
    (RUNTIME / 'release/strata-online-upload.private.json').write_bytes((json.dumps(manifest, indent=2)+'\n').encode('utf-8'))
    template = (RUNTIME / 'release/invoke-online-round.ps1').read_text(encoding='utf-8')
    template = template.replace('qa-paired-v22-20260917-r1', 'qa-paired-v22-20260917-r2')
    template = template.replace('qa_paired_v22_20260917_r1', 'qa_paired_v22_20260917_r2')
    template = template.replace(sha(original), sha(output))
    old_batch = next(line.split("'")[1] for line in template.splitlines() if line.startswith('$BatchHash ='))
    template = template.replace(old_batch, sha(ROOT / 'tools/run_qa_template_batch.py'))
    (RUNTIME / 'release/invoke-strata-online-round.ps1').write_bytes(template.encode('utf-8'))
    print(json.dumps({'ok': True, 'total': len(plan['cases']), 'per_turn_model_strata': True,
                      'plan_sha256': sha(output), 'automatic_replay': False}))


if __name__ == '__main__': main()
