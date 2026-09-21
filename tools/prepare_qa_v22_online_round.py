"""Add independently reproduced defects and bind one new no-replay online round."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.codex_runtime/qa-routing-v22'


def main():
    plan = json.loads((RUNTIME / 'paired-failures.private.json').read_text(encoding='utf-8'))
    ledger = json.loads((ROOT / 'tests/qa_regression/question_ledger_20260916.json').read_text(encoding='utf-8'))
    by_id = {row['case_id']: row for row in ledger['rows']}
    ids = ['TPL-FACD6F5FE05C74FC', 'TPL-01EEE414179DB624', 'TPL-F84133F736C1F86F']
    existing = {row['case_id'] for row in plan['cases']}
    extra = []
    for case_id in ids:
        if case_id in existing:
            continue
        row = by_id[case_id]
        if row['collection_status'] != 'collected':
            raise ValueError('Original evidence unavailable')
        extra.append({'case_id': case_id, 'prompt': row['prompt'], 'prompt_mode': 'technical',
                      'cohort': 'v22_reproduced_statistical_scope', 'category': row['category'],
                      'previous_result_sha256': row['result_sha256'],
                      'expected': 'independent review of original question and final answer; preserved units/source/time/statistics',
                      'review_scope': 'CV interpretation conditions and trend time-scale disclosure; no upstream three-signal consistency claim'})
    plan['cases'] = extra + plan['cases']
    plan['v22_reproduced_extra'] = len(extra)
    output = RUNTIME / 'templates.remaining.plan.private.json'
    if output.exists():
        raise ValueError('Online plan already frozen; do not overwrite/replay')
    output.write_bytes((json.dumps(plan, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
    stage = 'C:/Users/Administrator/AppData/Local/Temp/qa-paired-v22-20260917-r1'
    def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
    template = (ROOT / 'tools/start_qa_paired_failure_batch.ps1').read_text(encoding='utf-8')
    for old, new in [
        ('qa-paired-v21-20260916-r2', 'qa-paired-v22-20260917-r1'),
        ('qa_paired_v21_20260916_r2', 'qa_paired_v22_20260917_r1'),
        ('8F54088673A5B9B5D6C156C0ABF536704008184A029CE252AC80D1042FA9AAC2', sha(output)),
        ('6CE94C62DA0487376223DACDBB72D0075812208FE5194D958F5CF65C2667F9D6', sha(ROOT / 'tools/run_qa_template_batch.py')),
    ]:
        if template.count(old) != 1: raise ValueError('Reviewed launch binding changed')
        template = template.replace(old, new)
    (RUNTIME / 'release/invoke-online-round.ps1').write_bytes(template.encode('utf-8'))
    manifest = {'stage': stage, 'total': len(plan['cases']), 'plan_sha256': sha(output),
                'files': [
                    {'local': str(output), 'remote': stage + '/templates.remaining.plan.json'},
                    {'local': str(ROOT / 'tools/run_qa_template_batch.py'), 'remote': stage + '/batch.py'},
                    {'local': str(ROOT / 'tools/run_qa_live_case.py'), 'remote': stage + '/collector.py'},
                    {'local': str(ROOT / 'tools/start_qa_batch_independent.ps1'), 'remote': stage + '/start_qa_batch_independent.ps1'},
                ]}
    (RUNTIME / 'release/online-upload.private.json').write_bytes((json.dumps(manifest, indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok': True, 'total': len(plan['cases']), 'additional_reproduced': len(extra),
                      'plan_sha256': sha(output), 'automatic_replay': False}))


if __name__ == '__main__': main()
