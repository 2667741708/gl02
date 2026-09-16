"""Freeze all 822 initial failed/partial cases, including later defects; no POST."""
import hashlib
import json
from pathlib import Path

from validate_qa_initial_828_review import validate

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    runtime = ROOT / '.codex_runtime/qa-routing-v25'
    release = runtime / 'release'
    output = runtime / 'failure-round.plan.private.json'
    manifest_path = release / 'online-upload.private.json'
    if output.exists() or manifest_path.exists():
        raise ValueError('Frozen version round exists; do not overwrite or replay')
    validate(ROOT / 'tests/qa_regression/initial_828_semantic_review_20260916.json')
    summary = json.loads((ROOT / 'tests/qa_regression/initial_semantic_summary_20260917.json').read_text(encoding='utf-8'))
    ledger = json.loads((ROOT / 'tests/qa_regression/question_ledger_20260916.json').read_text(encoding='utf-8'))['rows']
    originals = {r['case_id']: r for r in ledger}
    plan = json.loads((ROOT / '.codex_runtime/qa-routing-v24/failure-round.plan.private.json').read_text(encoding='utf-8'))
    old = {r['case_id']: r for r in plan['cases']}
    snapshot = json.loads((release / 'post-record-snapshot.json').read_text(encoding='utf-8'))
    if not snapshot['ok'] or snapshot['head'] != '6ec408b17db75a040028fdee843cbd1b5b63c5ff':
        raise ValueError('Unverified V25 deployed production snapshot')
    approved = {'9111be230d48e53a385a28930fb8cf6972767c83e93c0db51f6b331a534e30fb',
                'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'}
    if snapshot['model_identity']['digest'] not in approved:
        raise ValueError('Model is not approved Qwen')
    cases = []
    for reviewed in summary['rows']:
        if reviewed['status'] not in {'failed', 'partial'}:
            continue
        original = originals[reviewed['case_id']]
        if hashlib.sha256(original['prompt'].encode()).hexdigest() != reviewed['original_prompt_sha256'] or original['result_sha256'] != reviewed['original_result_sha256']:
            raise ValueError('Original prompt/result binding changed')
        case = dict(old.get(reviewed['case_id']) or {
            'case_id': original['case_id'], 'prompt': original['prompt'], 'prompt_mode': 'technical',
            'cohort': 'first_collection_failed_or_partial', 'category': original['category'],
            'previous_result_sha256': original['result_sha256'], 'original_prompt_sha256': reviewed['original_prompt_sha256'],
            'source_path': original['source_path'], 'source_line': original['source_line'],
            'issue_ids': reviewed['issue_ids'], 'expected': 'independent full final-answer and source review required'})
        if case['prompt'] != original['prompt']:
            raise ValueError('Original question changed')
        case.update(initial_semantic_status=reviewed['status'], cohort='first_collection_failed_or_partial',
                    previous_result_sha256=original['result_sha256'],
                    original_prompt_sha256=reviewed['original_prompt_sha256'])
        cases.append(case)
    if len(cases) != 822:
        raise ValueError('Final initial failed/partial scope changed')
    extra_ids = ['TPL-FACD6F5FE05C74FC', 'TPL-01EEE414179DB624']
    by_id = {c['case_id']: c for c in cases}
    priority = ['TPL-C5DF79304112ED85', 'TPL-342113EAB17420C6', 'TPL-BE97AA4EAD567003', 'TPL-A60B0CD794D49E48', *extra_ids]
    if len(by_id) != 822 or 'TPL-10C8C8FAF2C694EF' in by_id or not set(priority) <= set(by_id):
        raise ValueError('Invalid unique scope or forbidden unknown case')
    plan.update(phase='after-v25', round='paired-v25-20260917-r1', production_commit=snapshot['head'],
        runtime_hashes=snapshot['runtime_hashes'], catalog_sha256=snapshot['catalog_sha256'],
        model_identity=snapshot['model_identity'], collector_sha256=sha(ROOT / 'tools/run_qa_live_case.py'),
        cases=[by_id[k] for k in priority] + [c for c in cases if c['case_id'] not in priority],
        first_collection_confirmed_failed=637, first_collection_partial=185, original_first_eight=0,
        initial_semantic_summary_sha256=sha(ROOT / 'tests/qa_regression/initial_semantic_summary_20260917.json'),
        policy='Explicitly authorized new V25 round after deployed code: 822 initial failed/partial original questions unchanged, including two V22 defects now confirmed initial partial; one POST per case; no automatic replay; fixed current approved Qwen digest. Model differs from V24: no causal code-only accuracy claim.')
    plan['model_identity'].pop('approved_digests', None)
    output.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    template = (ROOT / '.codex_runtime/qa-routing-v24/release/invoke-online-round.ps1').read_text(encoding='utf-8')
    old_sha = sha(ROOT / '.codex_runtime/qa-routing-v24/failure-round.plan.private.json').upper()
    if template.count(old_sha) != 1:
        raise ValueError('Reviewed launch hash binding changed')
    template = template.replace(old_sha, sha(output).upper()).replace('v24', 'v25').replace('V24', 'V25')
    batch, starter = ROOT / 'tools/run_qa_template_batch.py', ROOT / 'tools/start_qa_batch_independent.ps1'
    if sha(batch) != 'cb41506e30253d192204fed77f94903d2c771fb820939e122ff1ca0760deabf7' or sha(starter) != '80849af1c05240a9eb7a0441b28ae2261d33df9cdef5a41bf534dc037ad23df3':
        raise ValueError('Reviewed serial no-replay tools changed')
    (release / 'invoke-online-round.ps1').write_bytes(template.encode('utf-8'))
    stage = 'C:/Users/Administrator/AppData/Local/Temp/qa-paired-v25-20260917-r1'
    manifest = {'stage': stage, 'total': len(cases), 'plan_sha256': sha(output), 'files': [
        {'local': str(output), 'remote': stage + '/templates.remaining.plan.json'},
        {'local': str(batch), 'remote': stage + '/batch.py'},
        {'local': str(ROOT / 'tools/run_qa_live_case.py'), 'remote': stage + '/collector.py'},
        {'local': str(starter), 'remote': stage + '/start_qa_batch_independent.ps1'}]}
    manifest_path.write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'total': len(cases), 'initial_failed': 637, 'initial_partial': 185, 'model_digest': snapshot['model_identity']['digest'], 'no_automatic_replay': True}))


if __name__ == '__main__':
    main()
