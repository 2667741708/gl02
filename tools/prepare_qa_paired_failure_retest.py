"""Freeze original questions and failure counts for an explicitly authorized new round."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from audit_qa_knowledge_oracles import parse_cases, inspect

ROOT=Path(__file__).resolve().parents[1]


def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def normalize(text):return ''.join(text.split())
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise ValueError('Frozen plan already exists; do not overwrite')
    path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    ledger=load(ROOT/'tests/qa_regression/question_ledger_20260916.json')
    entries=ledger['rows'] if isinstance(ledger,dict) and 'rows' in ledger else ledger['questions']
    failures=[row for row in entries if row['collection_status']=='collected'
              and row['answer_review_status'] in ('confirmed_failed_manual','confirmed_failed_fixed_response')]
    if len(failures)!=405 or len({row['case_id'] for row in failures})!=405:
        raise ValueError('First collection failure denominator changed')
    kb=parse_cases((ROOT/'PT/三规二制高炉长工长知识库测试题库.md').read_text(encoding='utf-8'))
    blocked={row['oracle_id'] for row in inspect(kb) if row['state']=='oracle_blocked'}
    by_question={}
    for row in kb:by_question.setdefault(normalize(row['question']),[]).append(row)
    cases=[]
    for row in load(ROOT/'tests/qa_regression/live_cases.v1.json')['cases']:
        cases.append({**row,'cohort':'first_eight','prompt_mode':'spoken'})
    for row in failures:
        matching=by_question.get(normalize(row['prompt']),[])
        invalid=any(k['oracle_id'] in blocked for k in matching)
        case={'case_id':row['case_id'],'prompt':row['prompt'],'prompt_mode':'technical',
              'cohort':'first_collection_failed','category':row['category'],
              'previous_review':row['answer_review_status'],'previous_result_sha256':row['result_sha256'],
              'original_prompt_sha256':hashlib.sha256(row['prompt'].encode('utf-8')).hexdigest(),
              'source_path':row['source_path'],'source_line':row['source_line'],
              'issue_ids':row['issue_ids'],'oracle_blocked':invalid,
              'expected':'independent manual final-answer review required'}
        if matching and not invalid and len(matching)==1:
            k=matching[0]
            case.update(oracle_id=k['oracle_id'],expected={'original_text':k['expected'],
                'source_reference_id':k['reference_id']})
        cases.append(case)
    snapshot=load(args.snapshot)
    if not snapshot.get('ok'):raise ValueError('Unverified production snapshot')
    plan={'schema':'bf.qa.paired-failure-round.v1','requirement_id':'REQ-QA-PAIRED-FAILURE-RETEST-20260916',
          'phase':'after-v21','round':'paired-v21-20260916-r1','production_commit':snapshot['head'],
          'collector_sha256':hashlib.sha256((ROOT/'tools/run_qa_live_case.py').read_bytes()).hexdigest(),
          'catalog_sha256':snapshot['catalog_sha256'],'runtime_hashes':snapshot['runtime_hashes'],
          'model_identity':snapshot['model_identity'],'cases':cases,
          'first_collection_counts':dict(Counter(row['answer_review_status'] for row in entries)),
          'first_collection_confirmed_failed':len(failures),'original_first_eight':8,
          'oracle_blocked_attempts':sum(bool(row.get('oracle_blocked')) for row in cases),
          'accuracy_rule':'Correct complete final answer / valid independently scored cases; not nonempty text.',
          'answer_success_rule':'Complete useful answer / valid attempted cases; clear inability alone is not answer success.',
          'policy':'new explicitly authorized round;one POST per case;no automatic replay;original questions unchanged'}
    write(args.output,plan)
    print(json.dumps({'ok':True,'total':len(cases),'failed_cohort':len(failures),
                      'oracle_blocked':plan['oracle_blocked_attempts']},ensure_ascii=False))


if __name__=='__main__':main()
