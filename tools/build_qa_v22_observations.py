"""Project explicit primary-agent full-answer decisions; never infer semantic pass."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DECISIONS={
    'TPL-FACD6F5FE05C74FC': ('failed', '要求当前半小时三段压差对比，实际工具0次，未提供比较并错误宣称未连接实时系统。', ['QAOPT-R01','QAOPT-R03']),
    'TPL-01EEE414179DB624': ('failed', '要求单个炉体温度半小时稳定性，实际工具0次，缺数据且错误宣称无法访问已授权传感器。', ['QAOPT-R01','QAOPT-R03']),
    'TPL-F84133F736C1F86F': ('passed', '完整半小时统计、单位与只读来源同成功工具结果对应；CV按标准差/均值复算一致，首末/回归冲突与最近方向范围明确。', []),
    'LIVE-001': ('passed', '完整说明允许工艺/数据/诊断用途及证据限制，明确不生成或执行代码，不查实时。', []),
    'LIVE-002': ('passed', '仅用给定2/4/6逐步计算均值4与总体标准差sqrt(8/3)，分母为3；无现场查询或程序示例。', []),
    'LIVE-003': ('partial', '假设数据变化量与不可单凭顶压认定恶化的结论正确；其控制/风量不变即阻力不变等条件性解释过强，且请求后模型身份未核实。', ['QAOPT-E06','QAOPT-O01']),
}


def main():
    private=ROOT/'.codex_runtime/qa-routing-v22/snapshots/results.private.json'
    data=json.loads(private.read_text(encoding='utf-8'))
    by_id={row['case_id']:row for row in data['rows']}
    progress={row['case_id']:row for row in data['progress']['results']}
    if set(by_id)!=set(DECISIONS):raise ValueError('Reviewed scope mismatch')
    rows=[]
    for case_id,(status,reason,issues) in DECISIONS.items():
        original=by_id[case_id]
        if original['request_count']!=1 or not original['terminated']:raise ValueError('Transport incomplete')
        rows.append({'case_id':case_id,'status':status,'reason':reason,'issue_ids':issues,
                     'result_sha256':original['result_file_sha256'],
                     'model_identity_samples':{key:progress[case_id].get(key) for key in ['before_identity','after_identity','post_turn_identity']},
                     'route':original['final'].get('answer_route'),
                     'transport_complete':True,'eligible_stable_sample':progress[case_id].get('post_turn_identity')=='matched'})
    stable=[row for row in rows if row['eligible_stable_sample']]
    value={'schema':'bf.qa.v22.independent-observations.v1','requirement_id':'REQ-QA-PAIRED-FAILURE-RETEST-20260916',
           'production_commit':'e43c5c9010c82fe4324c15602d62b1f2eefde3c4',
           'method':'Explicit primary-agent decisions after complete question/answer/tool-result review; script only projects decisions and checks identities.',
           'planned':416,'attempted':6,'proven_unsent':410,'stable_identity_sampled':len(stable),
           'stable_sample_correct_complete':sum(row['status']=='passed' for row in stable),
           'stable_sample_accuracy':3/5,'transport_complete':6,'transport_rate':1.0,
           'accuracy_scope':'Five observed stable samples only, including two controls; not 405 baseline failure recovery or full assistant accuracy.',
           'first_405_failed_attempted':0,'initial_828_rule_screening_accuracy_accepted':False,'rows':rows}
    output=ROOT/'tests/qa_regression/routing_v22_paired_observations_20260917.json'
    output.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'ok':True,'attempted':6,'stable_sample':5,'passed':3,'failed':2,'partial_unstable':1}))


if __name__=='__main__':main()
