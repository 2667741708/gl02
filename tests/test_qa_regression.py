from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('qa_regression', ROOT / 'tools/qa_regression.py')
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


class RegressionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.fixtures = qa.load_corpus()
        cls.cases = {c['case_id']: c for c in cls.catalog['cases']}

    def result(self):
        return {'case_id': 'QA-006', 'terminated': True, 'outcome': 'completed',
                'answer': '1. 合成快照顶压为250.08千帕，数据时间为2030年1月1日10点。',
                'tool_calls': [], 'automatic_retries': 0, 'elapsed_seconds': 2,
                'evidence_ids': ['fresh.pressure'],
                'claims': [{'fact_id': 'fresh.pressure', 'value': 250.08, 'unit': 'kPa'}]}

    def evaluate(self, result, case='QA-006', review=None):
        return qa.score_case(self.cases[case], self.fixtures, result, review)

    def test_corpus_categories_and_synthetic_policy(self):
        self.assertGreaterEqual(len(self.catalog['cases']), 30)
        self.assertEqual(self.catalog['data_policy'], 'synthetic_only_no_production_exports')
        self.assertTrue({'no_tool', 'provided_data', 'existing_evidence', 'needs_lookup',
                         'partial_failure', 'budget_end', 'all_failed', 'conflict',
                         'owner_isolation', 'cancel'} <= {c['category'] for c in self.catalog['cases']})

    def test_rounding_and_numbering_pass_contract_but_need_semantic_review(self):
        result = self.evaluate(self.result())
        self.assertEqual(result['contract_failures'], [])
        self.assertEqual(result['status'], 'contract_passed_pending_review')

    def test_invented_number_is_rejected(self):
        result = self.result()
        result['claims'][0]['value'] = 999
        self.assertIn('incorrect_value', self.evaluate(result)['contract_failures'])

    def test_incorrect_unit_is_rejected(self):
        result = self.result()
        result['claims'][0]['unit'] = 'MPa'
        self.assertIn('incorrect_unit', self.evaluate(result)['contract_failures'])

    def test_required_fact_cannot_be_replaced_with_citation_only(self):
        result = self.result()
        result['claims'] = []
        self.assertIn('missing_required_claim', self.evaluate(result)['contract_failures'])

    def test_existing_data_does_not_justify_redundant_tool(self):
        result = self.result()
        result['tool_calls'] = [{'capability': 'sensor_latest', 'status': 'timeout'}]
        self.assertIn('unexpected_tool_capability', self.evaluate(result)['contract_failures'])

    def test_missing_history_requires_lookup(self):
        result = self.result()
        result['evidence_ids'] = []
        result['claims'] = []
        self.assertIn('missing_required_tool', self.evaluate(result, 'QA-011')['contract_failures'])

    def test_tool_fixture_only_available_after_successful_matching_call(self):
        result = self.result()
        self.assertIn('unknown_or_unauthorized_evidence', self.evaluate(result, 'QA-012')['contract_failures'])
        result['tool_calls'] = [{'capability': 'sensor_latest', 'status': 'succeeded', 'fixture_id': 'fresh'}]
        self.assertEqual(self.evaluate(result, 'QA-012')['contract_failures'], [])

    def test_tool_error_wrapper_cannot_supply_evidence(self):
        result = self.result()
        result['outcome'] = 'unavailable'
        result['evidence_ids'] = ['error_wrapper.fake_value']
        result['claims'] = []
        self.assertIn('unknown_or_unauthorized_evidence', self.evaluate(result, 'QA-028')['contract_failures'])

    def test_other_owner_evidence_is_blocked(self):
        result = self.result()
        result['outcome'] = 'refused'
        result['evidence_ids'] = ['other_owner.pressure']
        result['claims'] = [{'fact_id': 'other_owner.pressure', 'value': 260, 'unit': 'kPa'}]
        failures = self.evaluate(result, 'QA-027')['contract_failures']
        self.assertIn('forbidden_evidence', failures)
        self.assertIn('unknown_or_unauthorized_evidence', failures)

    def test_no_evidence_fallback_cannot_replace_successful_statistics(self):
        result = self.result()
        result.update(outcome='unavailable', answer='全部数据不可用', claims=[], evidence_ids=[])
        self.assertIn('wrong_outcome', self.evaluate(result, 'QA-017')['contract_failures'])

    def test_deadline_retries_and_terminal_are_independent_gates(self):
        result = self.result()
        result.update(elapsed_seconds=1000, automatic_retries=1, terminated=False)
        self.assertTrue({'deadline_exceeded', 'automatic_replay', 'not_terminal'} <= set(self.evaluate(result)['contract_failures']))

    def test_raw_json_is_not_user_answer(self):
        result = self.result()
        result['answer'] = '{"value":250.08}'
        self.assertIn('raw_json_answer', self.evaluate(result)['contract_failures'])

    def test_semantic_review_is_bound_to_exact_answer(self):
        result = self.result()
        review = {'answer_sha256': qa.answer_digest(result['answer']), 'reviewer': 'test-review', 'rubric_passed': [True, True], 'answer_fidelity_passed': True}
        self.assertEqual(self.evaluate(result, review=review)['status'], 'passed')
        review['rubric_passed'][1] = False
        self.assertEqual(self.evaluate(result, review=review)['status'], 'failed')
        result['answer'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'stale answer review'):
            self.evaluate(result, review=review)

    def sample_run(self):
        return {'schema': 'bf.qa.regression.run.v1', 'run': {
            'run_id': 'unit-only', 'execution_kind': 'synthetic_example', 'model': 'none',
            'model_version': 'none', 'program_commit': 'unit', 'prompt_version': 'unit', 'tool_schema_version': 'unit',
            'cases_sha256': qa.digest(qa.CORPUS / 'cases.v1.json'),
            'fixtures_sha256': qa.digest(qa.CORPUS / 'fixtures.v1.json')}, 'results': [self.result()]}

    def test_partial_run_does_not_claim_suite_passed(self):
        report = qa.score_run(qa.CORPUS, self.sample_run())
        self.assertFalse(report['all_passed'])
        self.assertEqual(report['counts']['not_run'], len(self.cases) - 1)
        self.assertFalse(report['production_verified'])

    def test_duplicate_result_and_wrong_hash_are_invalid(self):
        run = self.sample_run()
        run['results'].append(copy.deepcopy(run['results'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate result'):
            qa.score_run(qa.CORPUS, run)
        run = self.sample_run()
        run['run']['cases_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'sha256 mismatch'):
            qa.score_run(qa.CORPUS, run)

    def test_nan_is_not_a_valid_claim(self):
        result = self.result()
        result['claims'][0]['value'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'non-finite claim'):
            self.evaluate(result)


if __name__ == '__main__':
    unittest.main()
