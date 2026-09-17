"""Quiet, one-launch supervisor: GET-only waiting, then one pinned serial batch."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

NAME = 'chiqiongblastfuenace:latest'
PIN = 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
MANAGER_SHA = '1f871a8bbbaa553233d318b3d019a5a63e68be38d0f0caa7d29cca731d44434f'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    temporary = path.with_suffix('.next')
    temporary.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    temporary.replace(path)


def identity_matches(tags, resident):
    if not isinstance(tags, dict) or not isinstance(resident, dict):
        return False
    if not isinstance(tags.get('models'), list) or not isinstance(resident.get('models'), list):
        return False
    if any(not isinstance(row, dict) for row in tags['models'] + resident['models']):
        return False
    alias = [r for r in tags['models'] if r.get('name') == NAME]
    version = [r for r in tags['models'] if r.get('name') == 'chiqiongblastfuenace:1']
    loaded = resident['models']
    return (len(alias) == len(version) == len(loaded) == 1 and
            alias[0].get('digest') == version[0].get('digest') == loaded[0].get('digest') == PIN and
            loaded[0].get('name') == NAME)


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def readiness_status():
    try:
        value = get_json('http://127.0.0.1:8093/api/ollama/status')
        return isinstance(value, dict) and all(value.get(k) is True for k in ('ok', 'proxy_ok', 'ollama_ok', 'model_ok'))
    except Exception:
        return False


def observe():
    try:
        tags = get_json('http://127.0.0.1:11434/api/tags')
        resident = get_json('http://127.0.0.1:11434/api/ps')
        if not identity_matches(tags, resident):
            return False, 'fixed_model_identity_not_ready'
        if not readiness_status():
            return False, 'assistant_readiness_not_ready'
        # Status calls can outlive a model change; do not accept the earlier sample.
        tags = get_json('http://127.0.0.1:11434/api/tags')
        resident = get_json('http://127.0.0.1:11434/api/ps')
        return (True, 'fixed_identity_verified') if identity_matches(tags, resident) else (False, 'fixed_model_identity_not_ready')
    except Exception:
        return False, 'model_metadata_unavailable'


def validate_plan(plan):
    identity = plan.get('model_identity')
    if not isinstance(identity, dict) or identity.get('name') != NAME or identity.get('digest') != PIN or identity.get('approved_digests') != [PIN]:
        raise ValueError('single_frozen_model_required')
    cases = plan.get('cases')
    if not isinstance(cases, list) or len(cases) != 822:
        raise ValueError('original_failure_cohort_required')
    ids = [case['case_id'] for case in cases]
    if len(set(ids)) != 822 or 'TPL-10C8C8FAF2C694EF' in ids:
        raise ValueError('uncertain_or_duplicate_original_forbidden')
    for case in cases:
        if not isinstance(case['case_id'], str) or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in case['case_id']):
            raise ValueError('unsafe_case_identifier')


def verify_inputs(stage, root, manifest, expected_manifest_sha):
    if sha(stage / 'manifest.private.json') != expected_manifest_sha:
        raise ValueError('manifest_changed')
    if set(manifest['files']) != {'worker.py', 'batch.py', 'collector.py', 'templates.remaining.plan.json', 'start.ps1'}:
        raise ValueError('launch_file_set_invalid')
    for name, expected in manifest['files'].items():
        if sha(stage / name) != expected:
            raise ValueError('launch_file_changed')
    if sha(Path('F:/Ollama/model-switch/manage_ollama_model_switch.ps1')) != MANAGER_SHA:
        raise ValueError('fixed_manager_changed')
    plan = read(stage / 'templates.remaining.plan.json')
    validate_plan(plan)
    if sha(root / '数据库同步和存取/config/点位语义目录.json') != plan['catalog_sha256']:
        raise ValueError('point_catalog_changed')
    for relative, expected in plan['runtime_hashes'].items():
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()) or sha(target) != expected:
            raise ValueError('production_runtime_changed')
    return plan


def run(args):
    stage, root, output = args.stage.resolve(), args.root.resolve(), args.output.resolve()
    if not output.is_relative_to(root / 'logs') or output == root / 'logs':
        raise ValueError('output_outside_logs')
    manifest = read(stage / 'manifest.private.json')
    plan = verify_inputs(stage, root, manifest, args.manifest_sha256)
    claim = read(output / 'launch.claim')
    if claim.get('manifest_sha256') != args.manifest_sha256 or claim.get('automatic_replay') is not False:
        raise ValueError('launch_claim_invalid')
    with (output / 'worker.claim').open('x', encoding='utf-8') as stream:
        json.dump({'pid': os.getpid(), 'manifest_sha256': args.manifest_sha256, 'created_at': time.time()}, stream)
    state = {'schema': 'bf.qa.background-supervisor.v1', 'requirement_id': 'OPS-QA-QUIET-ORIGINAL-RETEST-20260918',
             'pid': os.getpid(), 'state': 'waiting_for_fixed_model', 'total': len(plan['cases']),
             'requests': 0, 'completed': 0, 'automatic_replay': False, 'model_management_operations': 0,
             'manifest_sha256': args.manifest_sha256, 'plan_sha256': sha(stage / 'templates.remaining.plan.json'),
             'application_version': 'V26', 'batch_progress_path': str(output / 'batch/progress.json'),
             'started_at': time.time(), 'stable_observations': 0}
    progress, stop = output / 'progress.json', output / 'STOP'
    write(progress, state)
    try:
        while True:
            if stop.exists():
                state['state'] = 'stopped_before_sending'
                return
            verify_inputs(stage, root, manifest, args.manifest_sha256)
            ready, reason = observe()
            state['reason'] = reason
            state['stable_observations'] = state['stable_observations'] + 1 if ready else 0
            state['updated_at'] = time.time()
            write(progress, state)
            if state['stable_observations'] >= 3:
                break
            time.sleep(30)
        spec = importlib.util.spec_from_file_location('sealed_qa_batch', stage / 'batch.py')
        batch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(batch)
        original_verify, original_budget = batch.verify, batch.require_request_budget

        def guarded_verify(plan, root, collector):
            verify_inputs(stage, root, manifest, args.manifest_sha256)
            if not identity_matches(get_json('http://127.0.0.1:11434/api/tags'), get_json('http://127.0.0.1:11434/api/ps')):
                raise RuntimeError('fixed_model_identity_changed_no_replay')
            identity = original_verify(plan, root, collector)
            if not identity_matches(get_json('http://127.0.0.1:11434/api/tags'), get_json('http://127.0.0.1:11434/api/ps')):
                raise RuntimeError('fixed_model_identity_changed_no_replay')
            return identity

        def guarded_budget(deadline, now=None):
            if stop.exists():
                raise RuntimeError('operator_stop_no_next_request')
            return original_budget(deadline, now)

        batch.verify, batch.model_ready, batch.require_request_budget = guarded_verify, readiness_status, guarded_budget
        state.update(state='running', reason='serial_original_retest', updated_at=time.time())
        write(progress, state)
        previous_argv = sys.argv
        try:
            sys.argv = [str(stage / 'batch.py'), '--root', str(root), '--plan', str(stage / 'templates.remaining.plan.json'),
                        '--collector', str(stage / 'collector.py'), '--output', str(output / 'batch'), '--execute']
            # pythonw has no console. Supply explicit private logs before batch.main prints.
            with (output / 'worker.stdout').open('x', encoding='utf-8', newline='\n') as out, (output / 'worker.stderr').open('x', encoding='utf-8', newline='\n') as err:
                previous_out, previous_err = sys.stdout, sys.stderr
                try:
                    sys.stdout, sys.stderr = out, err
                    batch.main()  # Exactly one batch invocation; no retry or resume loop.
                finally:
                    sys.stdout, sys.stderr = previous_out, previous_err
        finally:
            sys.argv = previous_argv
        result = read(output / 'batch/progress.json')
        state.update({key: result[key] for key in ('state', 'completed', 'requests')})
        state['final_answer_review'] = 'pending_semantic_review'
        state['reason'] = 'batch_completed' if result['state'] == 'completed' else 'batch_stopped_readonly_recovery_required'
    except Exception as exc:
        batch_progress = output / 'batch/progress.json'
        if batch_progress.exists():
            try:
                result = read(batch_progress)
                state.update({key: result[key] for key in ('completed', 'requests')})
            except Exception:
                state['batch_progress_unavailable'] = True
        state.update(state='blocked_no_replay', error_type=type(exc).__name__, reason='supervisor_precondition_or_runtime_failure')
    finally:
        state['updated_at'] = time.time()
        write(progress, state)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        parser.error('--execute required; no requests sent')
    run(args)
