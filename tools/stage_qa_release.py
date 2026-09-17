"""Upload one reviewed QA staging phase through the existing session broker."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=('v18', 'v19', 'v20', 'v21', 'v22', 'v23', 'v24', 'v25', 'v26'), required=True)
    parser.add_argument('--phase', choices=('preflight', 'activation'), required=True)
    args = parser.parse_args()
    recipe = json.loads((ROOT/'tools/qa_routing_release_extensions.json').read_text(encoding='utf-8'))[args.version]
    release = ROOT/f'.codex_runtime/qa-routing-{args.version}/release'
    candidate = release.parent/'candidate'
    stage = f'C:/Users/Administrator/AppData/Local/Temp/qa-routing-{args.version}-20260916-r1'
    if args.phase == 'preflight':
        files = [(candidate/name, name) for name in recipe['artifacts']]
        files += [(release/name, name) for name in ('scope-gate.json', 'recordability-expectation.json')]
        files += [(ROOT/'tools/remote_preflight_qa_routing_v3.ps1', 'remote_preflight_qa_routing_v3.ps1'),
                  (ROOT/'tools/audit_qa_release_baseline_readonly.py', 'audit_qa_release_baseline_readonly.py'),
                  (Path('C:/Users/hmw20/.codex/skills/deploy-8093-guarded-update/scripts/git_record_guard.py'), 'git_record_guard.py')]
    else:
        files = [(ROOT/'tools'/name, name) for name in ('remote_guarded_deploy_qa_routing_v3_8093.ps1', 'record_qa_routing_v3_version.ps1')]
        files += [(release/name, name) for name in ('delta-plan.json','operation.json','record-plan.json','invoke-deployment.ps1','invoke-record.ps1')]
    if any(not path.is_file() for path, name in files):
        raise ValueError('Missing reviewed local staging file; nothing uploaded')
    command = [sys.executable,'-X','utf8',str(ROOT/'tools/remote_22012_session.py'),'run','--']
    for path, name in files:
        command += ['--upload',f'{path.resolve()}={stage}/{name}']
    command += ['--upload-only','--workdir','F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW','--emit-timing-json']
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__': raise SystemExit(main())
