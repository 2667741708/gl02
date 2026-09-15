"""Validate the synthetic QA corpus or score collected fixture-based runs.

This tool never calls a model, an endpoint or production data. A trusted test
adapter must collect tool traces; model-generated self-reports are not evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'tests' / 'qa_regression'
OUTCOMES = {'completed', 'partial', 'clarification', 'unavailable', 'refused', 'cancelled'}
CAPABILITIES = {'sensor_latest', 'sensor_history', 'heat_quality', 'calculate'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def answer_digest(answer):
    return hashlib.sha256(answer.encode('utf-8')).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite_number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def load_corpus(directory=CORPUS):
    directory = Path(directory)
    catalog = read(directory / 'cases.v1.json')
    fixture_data = read(directory / 'fixtures.v1.json')
    require(catalog['schema'] == 'bf.qa.regression.cases.v1', 'unsupported case schema')
    require(fixture_data['schema'] == 'bf.qa.regression.fixtures.v1', 'unsupported fixture schema')
    require(catalog['data_policy'] == 'synthetic_only_no_production_exports', 'synthetic-only policy required')
    fixtures, all_facts = {}, {}
    for fixture in fixture_data['fixtures']:
        fid = fixture['id']
        require(fid not in fixtures, f'duplicate fixture: {fid}')
        require(fixture['scope'] in {'hypothetical', 'same_owner_same_furnace', 'other_owner'}, f'{fid}: scope')
        for fact in fixture['facts']:
            require(fact['id'] not in all_facts, f'duplicate fact: {fact["id"]}')
            require(finite_number(fact['value']), f'{fid}: non-finite fact')
            require(type(fact['decimals']) is int and 0 <= fact['decimals'] <= 9, f'{fid}: decimals')
            require(isinstance(fact['unit'], str), f'{fid}: unit')
            all_facts[fact['id']] = fact
        fixtures[fid] = fixture
    ids = set()
    for case in catalog['cases']:
        cid = case['case_id']
        require(re.fullmatch(r'QA-\d{3,}', cid) and cid not in ids, f'invalid/duplicate case: {cid}')
        ids.add(cid)
        require(type(case['version']) is int and case['version'] > 0, f'{cid}: version')
        require(case['provenance'] in {'synthetic', 'incident_pattern_rewritten_with_synthetic_data'}, f'{cid}: provenance')
        require(isinstance(case['prompt'], str) and case['prompt'].strip(), f'{cid}: prompt')
        require(case['rubric'] and all(isinstance(x, str) and x.strip() for x in case['rubric']), f'{cid}: rubric')
        refs = set(case['fixture_ids'])
        refs.update(x['fixture_id'] for x in case['tool_fixtures'])
        require(refs <= fixtures.keys(), f'{cid}: missing fixture')
        expected = case['expected']
        policy = expected['tool_policy']
        require(policy in {'forbidden', 'optional', 'required'}, f'{cid}: tool policy')
        allowed = set(expected['allowed_capabilities'])
        required = set(expected['required_capabilities'])
        require(required <= allowed <= CAPABILITIES, f'{cid}: capabilities')
        require(type(expected['max_tool_calls']) is int and expected['max_tool_calls'] >= 0, f'{cid}: tool limit')
        require(finite_number(expected['max_seconds']) and expected['max_seconds'] > 0, f'{cid}: time limit')
        require(policy != 'forbidden' or (not allowed and expected['max_tool_calls'] == 0), f'{cid}: forbidden tool contract')
        require(policy != 'required' or bool(required), f'{cid}: required capability missing')
        require(expected['allowed_outcomes'] and set(expected['allowed_outcomes']) <= OUTCOMES, f'{cid}: outcomes')
        fact_ids = {f['id'] for ref in refs for f in fixtures[ref]['facts']}
        require(set(expected['required_evidence']) <= fact_ids, f'{cid}: unavailable required evidence')
        require(set(expected['forbidden_evidence']) <= all_facts.keys(), f'{cid}: unknown forbidden evidence')
        require(not set(expected['required_evidence']) & set(expected['forbidden_evidence']), f'{cid}: conflicting evidence rules')
        require({x['capability'] for x in case['tool_fixtures']} <= allowed, f'{cid}: tool fixture capability')
        for ref in case['fixture_ids']:
            f = fixtures[ref]
            if f['scope'] == 'other_owner' or f['source_kind'] == 'tool_error':
                require(not set(expected['required_evidence']) & {v['id'] for v in f['facts']}, f'{cid}: unsafe required evidence')
    require(bool(ids), 'empty corpus')
    # Independent arithmetic oracle: no model or production runtime involved.
    if 'arithmetic' in fixtures:
        values = [2, 4, 6]
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        require(math.isclose(all_facts['arithmetic.mean']['value'], mean), 'mean oracle mismatch')
        require(math.isclose(all_facts['arithmetic.stddev']['value'], sd), 'population stddev oracle mismatch')
    return catalog, fixtures


def available_facts(refs, fixtures):
    return {fact['id']: fact for ref in refs for fact in fixtures[ref]['facts']
            if fixtures[ref]['scope'] != 'other_owner' and fixtures[ref]['source_kind'] != 'tool_error'}


def score_case(case, fixtures, result, review=None):
    expected = case['expected']
    failures = []
    def check(ok, reason):
        if not ok:
            failures.append(reason)
    require(type(result['terminated']) is bool, 'terminated must be boolean')
    require(type(result['automatic_retries']) is int and result['automatic_retries'] >= 0, 'invalid retry count')
    require(finite_number(result['elapsed_seconds']) and result['elapsed_seconds'] >= 0, 'invalid elapsed time')
    answer = result['answer']
    require(isinstance(answer, str), 'answer must be text')
    check(result['terminated'], 'not_terminal')
    check(result['outcome'] in expected['allowed_outcomes'], 'wrong_outcome')
    check(bool(answer.strip()), 'empty_answer')
    check(result['automatic_retries'] == 0, 'automatic_replay')
    check(result['elapsed_seconds'] <= expected['max_seconds'], 'deadline_exceeded')
    check(not expected['no_raw_json'] or not (answer.lstrip().startswith(('{', '[')) or '```json' in answer), 'raw_json_answer')
    calls = result['tool_calls']
    require(isinstance(calls, list), 'tool_calls must be list')
    check(len(calls) <= expected['max_tool_calls'], 'too_many_tools')
    evidence = available_facts(case['fixture_ids'], fixtures)
    allowed_pairs = {(v['capability'], v['fixture_id']) for v in case['tool_fixtures']}
    capabilities = set()
    for call in calls:
        cap = call['capability']
        require(call['status'] in {'succeeded', 'failed', 'timeout'}, 'invalid tool status')
        capabilities.add(cap)
        check(cap in expected['allowed_capabilities'], 'unexpected_tool_capability')
        if call['status'] == 'succeeded':
            pair = (cap, call['fixture_id'])
            check(pair in allowed_pairs, 'unexpected_tool_fixture')
            if pair in allowed_pairs:
                f = fixtures[call['fixture_id']]
                check(f['source_kind'] != 'tool_error' and f['scope'] != 'other_owner', 'unsafe_tool_evidence')
                evidence.update(available_facts([call['fixture_id']], fixtures))
    check(set(expected['required_capabilities']) <= capabilities, 'missing_required_tool')
    cited = result['evidence_ids']
    require(isinstance(cited, list) and all(isinstance(x, str) for x in cited), 'evidence_ids must be strings')
    check(set(cited) <= evidence.keys(), 'unknown_or_unauthorized_evidence')
    check(not set(cited) & set(expected['forbidden_evidence']), 'forbidden_evidence')
    check(set(expected['required_evidence']) <= set(cited), 'missing_required_evidence')
    require(isinstance(result['claims'], list), 'claims must be list')
    check(set(expected['required_evidence']) <= {c['fact_id'] for c in result['claims']}, 'missing_required_claim')
    for claim in result['claims']:
        fact = evidence.get(claim['fact_id'])
        check(fact is not None and claim['fact_id'] in cited, 'unbound_claim')
        if fact is None:
            continue
        require(finite_number(claim['value']), 'non-finite claim')
        tolerance = 0.5 * 10 ** -fact['decimals'] + 1e-10
        check(abs(claim['value'] - fact['value']) <= tolerance, 'incorrect_value')
        check(claim['unit'] == fact['unit'], 'incorrect_unit')
    # Do not use numeric regexes on prose: numbering, formula examples and
    # conditional statements need an independent content review.
    semantic = 'not_reviewed'
    if review is not None:
        require(review['answer_sha256'] == answer_digest(answer), 'stale answer review')
        require(isinstance(review['reviewer'], str) and review['reviewer'].strip(), 'reviewer required')
        checks = review['rubric_passed']
        require(isinstance(checks, list) and len(checks) == len(case['rubric']) and all(type(x) is bool for x in checks), 'review must cover every rubric item')
        require(type(review['answer_fidelity_passed']) is bool, 'full-answer fidelity review required')
        semantic = 'passed' if all(checks) and review['answer_fidelity_passed'] else 'failed'
    status = 'failed' if failures or semantic == 'failed' else ('passed' if semantic == 'passed' else 'contract_passed_pending_review')
    return {'case_id': case['case_id'], 'status': status, 'contract_failures': sorted(set(failures)), 'semantic_status': semantic}


def score_run(directory, run, reviews=None):
    catalog, fixtures = load_corpus(directory)
    require(run['schema'] == 'bf.qa.regression.run.v1', 'unsupported run schema')
    meta = run['run']
    require(meta['execution_kind'] in {'model_with_fixtures', 'synthetic_example'}, 'invalid execution kind')
    for field in ['run_id', 'model', 'model_version', 'program_commit', 'prompt_version', 'tool_schema_version']:
        require(isinstance(meta[field], str) and meta[field].strip(), f'missing run metadata: {field}')
    for filename, field in [('cases.v1.json', 'cases_sha256'), ('fixtures.v1.json', 'fixtures_sha256')]:
        require(meta[field] == digest(Path(directory) / filename), f'{field} mismatch')
    by_id = {c['case_id']: c for c in catalog['cases']}
    results, review_map = {}, {}
    for result in run['results']:
        cid = result['case_id']
        require(cid in by_id and cid not in results, f'unknown/duplicate result: {cid}')
        results[cid] = result
    if reviews is not None:
        require(reviews['run_id'] == meta['run_id'], 'review run mismatch')
        for review in reviews['items']:
            cid = review['case_id']
            require(cid in results and cid not in review_map, 'unknown/duplicate review')
            review_map[cid] = review
    rows = [score_case(c, fixtures, results[c['case_id']], review_map.get(c['case_id']))
            if c['case_id'] in results else {'case_id': c['case_id'], 'status': 'not_run'} for c in catalog['cases']]
    counts = {s: sum(r['status'] == s for r in rows) for s in ['passed', 'failed', 'contract_passed_pending_review', 'not_run']}
    return {'schema': 'bf.qa.regression.report.v1', 'run_id': meta['run_id'], 'execution_kind': meta['execution_kind'],
            'case_count': len(rows), 'counts': counts, 'all_passed': counts['passed'] == len(rows),
            'production_verified': False, 'pass_k': 'not_tested', 'concurrency': 'not_tested', 'results': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=CORPUS)
    parser.add_argument('--results', type=Path)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument('--list', action='store_true', help='Render the canonical case list as Markdown')
    args = parser.parse_args()
    try:
        catalog, fixtures = load_corpus(args.corpus)
        if args.list:
            require(not args.results and not args.reviews, '--list cannot be combined with scoring')
            print('Cases SHA-256: ' + digest(args.corpus / 'cases.v1.json'))
            print('| ID | Category | Tool policy | Question |\n|---|---|---|---|')
            for case in catalog['cases']:
                question = case['prompt'].replace('|', '\\|').replace('\n', ' ')
                print(f'| {case["case_id"]} | {case["category"]} | {case["expected"]["tool_policy"]} | {question} |')
            return 0
        if args.results:
            report = score_run(args.corpus, read(args.results), read(args.reviews) if args.reviews else None)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['all_passed'] and report['execution_kind'] == 'model_with_fixtures' else 1
        require(not args.reviews, '--reviews requires --results')
        print(json.dumps({'status': 'corpus_valid', 'case_count': len(catalog['cases']), 'fixture_count': len(fixtures),
                          'model_execution': 'not_run', 'production_verified': False}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'status': 'oracle_invalid', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
