"""Build a three-module semantic-scope candidate from verified production bytes."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.codex_runtime/qa-routing-v22'
BASELINES = {
    'ollama_proxy_server.py': '38c99c5fbde8e967549f0435a608b92db5648520a3e37622b686a391c004deb2',
    'qa_verified_facts.py': '461364b60dc6f4e987d0f997f9e3f1e973cd07ea503a44d8ea3760b681bd63fa',
    'qa_evidence_policy.py': '9ec4132ca8075ee9757663eedbab99aa793f330ebb0133880d57ece4fec7fe26',
}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Production needle not unique: ' + old[:100])
    return text.replace(old, new)


def main():
    source = json.loads((RUNTIME / 'baseline/source.private.json').read_text(encoding='utf-8'))
    candidate = RUNTIME / 'candidate'
    candidate.mkdir(exist_ok=False)
    diff = []
    for name, expected in BASELINES.items():
        text = source[name]['content']
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != expected:
            raise ValueError('Production baseline bytes changed: ' + name)
        (RUNTIME / 'baseline' / name).write_bytes(text.encode('utf-8'))
        if name != 'ollama_proxy_server.py':
            updated = (ROOT / '高炉前端数据/智能助手/backend' / name).read_text(encoding='utf-8-sig')
            # Preserve every production line outside the specific semantic addition.
            if name == 'qa_verified_facts.py':
                addition = updated[updated.index('def cv_contract'):updated.index('def timestamp')]
                updated = once(text, "VERSION = 'qa-verified-facts-v1'", "VERSION = 'qa-verified-facts-v2-statistical-scope'")
                updated = once(updated, 'def timestamp', addition + 'def timestamp')
            else:
                extra = updated[updated.index('MCP提供'):updated.index('正式炉况以')]
                updated = once(text, "VERSION = 'qa-evidence-no-code-v4'", "VERSION = 'qa-evidence-no-code-v5'")
                updated = once(updated, '正式炉况以', extra + '正式炉况以')
        else:
            updated = text
            old = '''                cv = (
                    float(stddev) / float(avg) * 100.0
                    if isinstance(avg, (int, float)) and isinstance(stddev, (int, float)) and float(avg) != 0
                    else None
                )
'''
            updated = once(updated, old, '')
            start = updated.index('                direction_text = ""')
            end = updated.index('                lines.append(', start)
            updated = updated[:start] + '                direction_text = qa_verified_facts.trend_context(statistics, unit_text, number)\n' + updated[end:]
            old = '''                    + (
                        f"CV = STDDEV_POP ÷ 均值 × 100% = {number(cv)}%；"
                        if cv is not None else
                        "CV = STDDEV_POP ÷ 均值 × 100%，均值为0或数据缺失，无法计算；"
                    )'''
            updated = once(updated, old, '                    + qa_verified_facts.render_cv(statistics, unit, number)')
            updated = once(updated, '''f"趋势 {statistics.get('trend') or '未知'}；"''', '''f"全窗口趋势 {statistics.get('trend') or '未知'}；"''')
            updated = once(updated, '''f"CV {number(stats.get('cv_percent'))}%。"''', '''+ qa_verified_facts.render_cv(stats, unit, number)''')
            updated = once(updated, '''f"极差 {number(stats.get('range'))}{unit}，CV {number(stats.get('cv_percent'))}%，"''', '''f"极差 {number(stats.get('range'))}{unit}；"\n                    + qa_verified_facts.render_cv(stats, unit, number) +''')
        updated = updated.replace('\r\n', '\n')
        ast.parse(updated, filename=name)
        (candidate / name).write_bytes(updated.encode('utf-8'))
        diff.extend(difflib.unified_diff(text.splitlines(True), updated.splitlines(True),
                                       fromfile='production/' + name, tofile='candidate/' + name))
    (RUNTIME / 'candidate.diff').write_bytes(''.join(diff).encode('utf-8'))
    print(json.dumps({'ok': True, 'targets': list(BASELINES), 'production_based': True}))


if __name__ == '__main__':
    main()
