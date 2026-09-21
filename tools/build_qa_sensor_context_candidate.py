"""Enforce explicit no-live and no-code policies before sensor context reads."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / '.codex_runtime/qa-routing-v45/candidate-r2'
PRIOR_SHA = 'a27bd42e7130ac7ba784f982b0b9240846cb1cf2c22f49e6d27809da505abb59'


def build_proxy(text):
    tree = ast.parse(text)
    node = next(item for item in ast.walk(tree) if isinstance(item, ast.FunctionDef) and item.name == 'prepare_qa_chat')
    lines = text.splitlines(keepends=True)
    original = ''.join(lines[node.lineno - 1:node.end_lineno])
    result = original

    def change(before, after):
        nonlocal result
        assert result.count(before) == 1, before
        result = result.replace(before, after)

    change('            source_task_plan = qa_task_plan.build_task_plan(question)\n', '')
    change('            current_snapshot = payload.get("current_snapshot")\n',
        '            source_task_plan = qa_task_plan.build_task_plan(question)\n'
        '            # REQ-QA-SENSOR-CONTEXT-SOURCE-GATE-20260917: preparation is an\n'
        '            # execution boundary too; downstream MCP gates are insufficient.\n'
        '            sensor_context_enabled = (not source_task_plan.get("no_live_lookup")\n'
        '                and not qa_evidence_policy.code_request_only(question))\n'
        '            current_snapshot = payload.get("current_snapshot")\n')
    change('                current_prompt_snapshot = snapshot_by_id(conn, current_snapshot_id)\n',
        '                # Preserve page-snapshot archival; it is not an evidence grant.\n'
        '                current_prompt_snapshot = (snapshot_by_id(conn, current_snapshot_id)\n'
        '                                           if sensor_context_enabled else None)\n')
    start = result.index('            try:\n                latest_pg_started = time.perf_counter()\n')
    end = result.index('            timing_ms["pg_context"] =', start)
    block = result[start:end]
    assert block.endswith('                trend_meta = {"trend_error": sanitize_model_exposure(exc)}\n')
    replacement = ('            timing_ms["pg_latest"] = 0.0\n'
        '            timing_ms["pg_trend"] = 0.0\n'
        '            if sensor_context_enabled:\n'
        + ''.join('    ' + line if line.strip() else line for line in block.splitlines(keepends=True))
        + '            else:\n'
        + '                trend_meta = {"sensor_context_skipped": True, "sensor_context_skip_reason": "source_policy"}\n')
    result = result[:start] + replacement + result[end:]
    change('[current_prompt_snapshot, pg_prompt_snapshot, latest_snapshot(conn)]',
        '[current_prompt_snapshot, pg_prompt_snapshot, latest_snapshot(conn) if sensor_context_enabled else None]')
    change('            if not trend_snapshots:\n', '            if sensor_context_enabled and not trend_snapshots:\n')
    change('                "context_mode": "latest_snapshot_plus_pg_8h_trend",\n',
        '                "context_mode": ("latest_snapshot_plus_pg_8h_trend" if sensor_context_enabled\n'
        '                                 else "source_plan_without_live_context"),\n')
    change('                "qa_source_task_plan": qa_task_plan.public_task_plan(source_task_plan),\n',
        '                "qa_source_task_plan": qa_task_plan.public_task_plan(source_task_plan),\n'
        '                "sensor_context_policy": {"schema": "qa-sensor-context-source-gate-v1",\n'
        '                    "enabled": bool(sensor_context_enabled), "skipped": not sensor_context_enabled},\n')
    lines[node.lineno - 1:node.end_lineno] = [result]
    changed = ''.join(lines)
    def functions(value):
        return {item.name: ast.dump(item, include_attributes=False) for item in ast.walk(ast.parse(value))
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}
    before, after = functions(text), functions(changed)
    assert set(before) == set(after)
    assert {name for name in before if before[name] != after[name]} == {'prepare_qa_chat'}
    return changed


def main(revision):
    target = ROOT / '.codex_runtime/qa-routing-v46' / ('candidate-' + revision)
    assert not target.exists()
    prior_raw = (PRIOR / 'package_manifest.private.json').read_bytes()
    assert hashlib.sha256(prior_raw).hexdigest() == PRIOR_SHA
    prior = json.loads(prior_raw)
    payloads = {name: (PRIOR / name).read_bytes() for name in prior['files']}
    for name, raw in payloads.items():
        assert hashlib.sha256(raw).hexdigest() == prior['files'][name]['sha256']
    payloads['ollama_proxy_server.py'] = build_proxy(payloads['ollama_proxy_server.py'].decode('utf-8')).encode('utf-8')
    inherited = sorted(set(payloads) - {'ollama_proxy_server.py'})
    assert len(payloads) == 16 and len(inherited) == 15
    for name, raw in payloads.items():
        assert b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf')
        ast.parse(raw.decode('utf-8'), filename=name)
    metadata = {**prior, 'candidate': 'v46-' + revision, 'prior_manifest_sha256': PRIOR_SHA,
        'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} for name, raw in sorted(payloads.items())},
        'inherited_v45_files_byte_identical': inherited, 'changed_modules': ['ollama_proxy_server.py'],
        'sensor_context_gate': 'qa-sensor-context-source-gate-v1',
        'gate_scope': 'explicit_no_live_user_data_and_code_only_no_snapshot_fallback',
        'nonrestricted_ordinary_and_abc_followup_path_unchanged': True,
        'request_page_snapshot_archival_preserved': True,
        'production_writes': 0, 'model_operations': 0}
    # Do not carry an old-version inheritance statement into the new closure.
    metadata.pop('inherited_v44_files_byte_identical', None)
    assert metadata['model_digest'] == 'e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124'
    assert not any(metadata[key] for key in ('model_switch_allowed', 'same_name_weight_replacement_allowed', 'fallback_model_allowed'))
    target.mkdir(parents=True)
    for name, raw in payloads.items():
        with (target / name).open('xb') as stream:
            stream.write(raw)
    raw = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with (target / 'package_manifest.private.json').open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'ok': True, 'candidate': metadata['candidate'], 'files': 16, 'inherited': 15,
        'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'production_sealed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=('r1', 'r2', 'r3', 'r4'), default='r1')
    main(parser.parse_args().revision)
