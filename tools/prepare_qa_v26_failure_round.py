"""Freeze the 822 original failure/partial cases for a new accepted version."""
import hashlib
import json
from pathlib import Path

from validate_qa_initial_828_review import validate

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v26'
    release = runtime / 'release'
    output = runtime / 'failure-round.plan.private.json'
    manifest_path = release / 'online-upload.private.json'
    if output.exists() or manifest_path.exists():
        raise ValueError('Version round exists; never overwrite or replay')
    validate(ROOT / 'tests/qa_regression/initial_828_semantic_review_20260916.json')
    summary_path = ROOT / 'tests/qa_regression/initial_semantic_summary_20260917.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    originals = {r['case_id']: r for r in json.loads((ROOT / 'tests/qa_regression/question_ledger_20260916.json').read_text(encoding='utf-8'))['rows']}
    previous_path = ROOT / '.codex_runtime/qa-routing-v25/failure-round.plan.private.json'
    plan = json.loads(previous_path.read_text(encoding='utf-8'))
    old = {r['case_id']: r for r in plan['cases']}
    snapshot = json.loads((release / 'post-record-snapshot.json').read_text(encoding='utf-8'))
    record = json.loads((release / 'accepted-version-record.json').read_text(encoding='utf-8'))
    approved = {'9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb', 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'}
    if not snapshot['ok'] or snapshot['head'] != record['head_after'] or not snapshot['single_resident_matches_alias'] or snapshot['model_identity']['digest'] not in approved:
        raise ValueError('Unverified accepted runtime or resident model identity')
    cases = []
    for reviewed in summary['rows']:
        if reviewed['status'] not in {'failed', 'partial'}: continue
        original = originals[reviewed['case_id']]
        if sha_text(original['prompt']) != reviewed['original_prompt_sha256'] or original['result_sha256'] != reviewed['original_result_sha256']:
            raise ValueError('Original source binding changed')
        case = dict(old[reviewed['case_id']])
        if case['prompt'] != original['prompt']: raise ValueError('Original question changed')
        case.update(initial_semantic_status=reviewed['status'], previous_result_sha256=original['result_sha256'], original_prompt_sha256=reviewed['original_prompt_sha256'])
        cases.append(case)
    by_id = {c['case_id']: c for c in cases}
    if len(cases) != 822 or set(by_id) != set(old) or 'TPL-10C8C8FAF2C694EF' in by_id:
        raise ValueError('Unexpected scope or forbidden uncertain original')
    ordered = [by_id[c['case_id']] for c in plan['cases']]
    plan.update(phase='after-v26', round='paired-v26-20260917-r1', production_commit=snapshot['head'],
                runtime_hashes=snapshot['runtime_hashes'], catalog_sha256=snapshot['catalog_sha256'], model_identity=dict(snapshot['model_identity']),
                collector_sha256=sha(ROOT / 'tools/run_qa_live_case.py'), cases=ordered,
                first_collection_confirmed_failed=636, first_collection_partial=186,
                initial_semantic_summary_sha256=sha(summary_path), predecessor_frozen_plan_sha256=sha(previous_path),
                policy='Explicitly authorized new V26 comparison after three-file chart repair. All 822 original prompts unchanged; one POST per case; no replay within this version. Current approved Qwen digest fixed per case; stop on identity drift. Compare model strata separately; no code-only causal accuracy claim.')
    plan['model_identity'].pop('approved_digests', None)
    output.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    template = (ROOT / '.codex_runtime/qa-routing-v25/release/invoke-online-round.ps1').read_text(encoding='utf-8')
    old_sha = sha(previous_path).upper()
    if template.count(old_sha) != 1: raise ValueError('Reviewed launch binding changed')
    template = template.replace(old_sha, sha(output).upper()).replace('v25', 'v26').replace('V25', 'V26')
    batch, starter = ROOT / 'tools/run_qa_template_batch.py', ROOT / 'tools/start_qa_batch_independent.ps1'
    if sha(batch) != 'cb41506e30253d192204fed77f94903d2c771fb820939e122ff1ca0760deabf7' or sha(starter) != '80849af1c05240a9eb7a0441b28ae2261d33df9cdef5a41bf534dc037ad23df3':
        raise ValueError('Reviewed serial once-only collector changed')
    (release / 'invoke-online-round.ps1').write_bytes(template.encode('utf-8'))
    stage = 'C:/Users/Administrator/AppData/Local/Temp/qa-paired-v26-20260917-r1'
    manifest = {'stage': stage, 'total': 822, 'plan_sha256': sha(output), 'files': [
        {'local': str(output), 'remote': stage + '/templates.remaining.plan.json'},
        {'local': str(batch), 'remote': stage + '/batch.py'},
        {'local': str(ROOT / 'tools/run_qa_live_case.py'), 'remote': stage + '/collector.py'},
        {'local': str(starter), 'remote': stage + '/start_qa_batch_independent.ps1'}]}
    manifest_path.write_bytes((json.dumps(manifest, indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'total': 822, 'initial_failed': 636, 'initial_partial': 186, 'model_digest': snapshot['model_identity']['digest']}))


def sha_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


if __name__ == '__main__':
    main()
