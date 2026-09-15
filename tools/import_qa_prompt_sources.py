"""Inventory local QA templates without executing/importing application code.

Public inventory contains sanitized prompts and source hashes; private run plan
retains reference answers. Neither expected answers nor system templates are
sent as user messages. Every extracted row has an explicit disposition.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

DOCS = [
    'PT/MCP可执行功能及口语调用模板.md',
    'PT/IMES_Vastbase_MCP指令模板全集.md',
    'PT/MCP少信息口语模板与无Prompt直连测试规范.md',
    'PT/8093近期炉况口语问答与安全边界Prompt模板.md',
    'PT/8093固定KV前缀模板规则池.md',
    'PT/三规二制高炉长工长知识库测试题库.md',
    'PT/智能体工具能力评估与153点位稳定Prompt路由方案.md',
    'docs/8093_8094_Prompt固定KV前缀与知识库回答链路_20260805.md',
    'docs/MCP_115变量诊断指标测试问题集.md',
]
HASH = lambda s: hashlib.sha256(s.encode('utf-8')).hexdigest()

def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))

def sanitized(s):
    s = re.sub(r'\d+#\d{8}-\d+', '[历史炉号]', s)
    address=r'(?:(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})'
    s = re.sub(r'(?i)(?:https?://)?'+address+r'(?::\d+)?', '[服务地址]', s)
    s = re.sub(r'(?i)((?:password|token|cookie|secret|密码)\s*[=:：]\s*)[^\s,，;；]+', r'\1[已隐藏]', s)
    return s

def disposition(text, kind):
    if kind == 'system_template': return 'contract_only', 'system_template_not_user_question'
    if kind == 'code_block': return 'contract_only', 'code_or_protocol_example'
    if not text.strip(): return 'skipped', 'blank'
    if text.startswith(('助手：', 'assistant:', '无数据：', '多样品：', '缺失值：', '查询失败：', '超时：', '权限不足：', '尚未发布：', '概念歧义：')):
        return 'skipped', 'assistant_example'
    if re.search(r'\{[^{}]+\}|<[^>]+>|\[填', text): return 'skipped', 'unresolved_placeholder'
    if text.startswith(('->', '→', 'MCP Client', '固定', '动态')): return 'contract_only', 'prompt_structure'
    if text in ('用户口语问题', '用户问题', '当前问题'): return 'contract_only', 'prompt_structure'
    if re.match(r'^[A-Za-z]:[\\/]', text): return 'contract_only', 'source_path_not_question'
    if not re.search(r'[\u4e00-\u9fff]', text): return 'contract_only', 'identifier_or_protocol'
    return 'ready', None

def collect(root):
    rows, sources = [], []
    def source(path):
        p = root/path
        if not p.exists():
            sources.append({'path':path, 'status':'missing'})
            return None
        text = p.read_text(encoding='utf-8-sig')
        sources.append({'path':path, 'status':'inventoried', 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        return text
    def add(path, line, text, kind='user_prompt', section='', **extra):
        status, reason = disposition(text, kind)
        rows.append(dict(case_id='TPL-'+HASH(path+'\0'+str(line)+'\0'+text)[:16].upper(),
            source_path=path, source_line=line, section=section, source_text=text,
            source_text_sha256=HASH(text), prompt=re.sub(r'^(用户|user)\s*[:：]\s*', '', text),
            kind=kind, source_status=status, skip_reason=reason, **extra))
    for path in DOCS:
        text=source(path)
        if text is None: continue
        fence=None; section=''; captured=[]; start=0; current=None
        for n,line in enumerate(text.splitlines(),1):
            if line.startswith('#') and fence is None: section=line.lstrip('# ').strip()
            match=re.match(r'^```(.*)$',line)
            if match:
                if fence is None: fence=match[1].strip(); captured=[]; start=n+1
                else:
                    if fence not in ('','text'): add(path,start,'\n'.join(captured),'code_block',section)
                    fence=None
                continue
            if fence is not None:
                if fence in ('','text'):
                    extra={}
                    if line.startswith('用户：'):
                        group=path+':'+section
                        extra=dict(conversation_group=group,turn_index=sum(r.get('conversation_group')==group for r in rows))
                    add(path,n,line.strip(),section=section,**extra)
                else: captured.append(line)
                continue
            if line.startswith('- 测试问题：'):
                add(path,n,line.split('：',1)[1],section=section,category='knowledge')
                current=rows[-1]
            elif line.startswith('- 标准答案：') and current:
                current['reference_answer']=line.split('：',1)[1].replace('<br>','\n')
            elif line.startswith('- 期望知识块：') and current:
                current['reference_ids']=re.findall(r'`([^`]+)`',line)
            elif line.startswith('|'):
                for q in re.findall(r'“([^”]+[？?。])”',line): add(path,n,q,section=section)
                if '测试问题集' in path and not re.search(r'^\|\s*(序|[-:])',line):
                    cols=[s.strip() for s in line.strip('|').split('|')]
                    if len(cols)>3 and re.search(r'[？?]|请|查询',cols[3]): add(path,n,cols[3],section=section)
    path='PT/智能体工具能力金标任务清单.v1.json'; text=source(path)
    if text:
        for c in json.loads(text)['cases']:
            line=text[:text.index('"case_id": "'+c['case_id']+'"')].count('\n')+1
            for i,prompt in enumerate(c.get('turns') or [c.get('prompt','')]):
                add(path,line,prompt,section=c['case_id'],category='gold',gold_contract=c,
                    conversation_group=c['case_id'] if c.get('turns') else None, turn_index=i)
                if c.get('fault_fixture'):
                    rows[-1].update(source_status='fixture_only',skip_reason='requires_fault_injection')
    for path in ('PT/智能体工具能力扩展生产回归.v1.json','PT/智能体工具能力口语化生产回归.v1.json'):
        text=source(path)
        if not text: continue
        spec=json.loads(text)
        for template in spec['templates']:
            marker=re.search(r'"template_id"\s*:\s*"'+re.escape(template['template_id'])+'"',text)
            line=text[:marker.start()].count('\n')+1
            for variable in spec['variables']:
                add(path,line,template['prompt'].format(**variable),section=template['template_id'],
                    expected_object=variable['object_id'],category='matrix',query_type=template['query_type'])
    path='tools/test_8093_colloquial_prompts.py'; text=source(path)
    if text:
        for node in ast.walk(ast.parse(text)):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='PromptCase':
                values=[ast.literal_eval(a) for a in node.args]
                if len(values)>=3:
                    add(path,node.lineno,values[2],section=str(values[0]),category=str(values[1]),
                        original_expectation=values[3] if len(values)>3 else '')
    path='高炉前端数据/frontend_dashboard_v3.server.html'; text=source(path)
    if text:
        m=re.search(r'const QA_MCP_RECOMMENDED_PROMPTS = Object.freeze\(\[(.*?)\]\)',text,re.S)
        if m:
            for q in re.finditer(r"['\"]([^'\"]+)['\"]",m[1]):
                add(path,text[:m.start(1)+q.start()].count('\n')+1,q[1],section='QA_MCP_RECOMMENDED_PROMPTS')
    # Bounded expansion from the documented backend prompt entrypoints.
    for p in sorted((root/'高炉前端数据/智能助手/backend').glob('*.py')):
        raw=p.read_text(encoding='utf-8-sig')
        if not re.search(r'PROMPT|prompt_template',raw): continue
        path=p.relative_to(root).as_posix(); source(path)
        try: tree=ast.parse(raw)
        except SyntaxError:
            sources[-1]['status']='syntax_error'; continue
        for node in ast.walk(tree):
            if not isinstance(node,(ast.Assign,ast.AnnAssign)): continue
            names=[n.id for n in ast.walk(node) if isinstance(n,ast.Name)]
            if not names or not re.search('PROMPT|prompt_template',names[0]): continue
            value=node.value
            try: value=ast.literal_eval(value)
            except (ValueError,TypeError): value=ast.get_source_segment(raw,value) or ''
            if isinstance(value,str): add(path,node.lineno,value,'system_template',names[0])
    # Explicit bounded inventory of literal MCP test inputs, never import tests.
    known={s['path'] for s in sources}
    for directory in ('tools','tests','高炉前端数据/智能助手/tests'):
        for p in sorted((root/directory).glob('*.py')):
            if not re.search(r'mcp|colloquial|prompt',p.name,re.I): continue
            path=p.relative_to(root).as_posix()
            if path in known: continue
            raw=source(path)
            try: tree=ast.parse(raw)
            except SyntaxError: sources[-1]['status']='syntax_error'; continue
            for node in ast.walk(tree):
                pairs=[]
                if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                    names=[n.id for n in node.targets if isinstance(n,ast.Name)]
                    if any(re.fullmatch(r'(?:QUESTION|PROMPT|question|prompt|raw)',name) for name in names):
                        add(path,node.lineno,node.value.value,section='literal_test_question')
                if isinstance(node,ast.Dict):
                    pairs=list(zip(node.keys,node.values))
                    is_user=any(isinstance(k,ast.Constant) and k.value=='role' and isinstance(v,ast.Constant) and v.value=='user' for k,v in pairs)
                    if is_user:
                        for k,v in pairs:
                            if isinstance(k,ast.Constant) and k.value=='content' and isinstance(v,ast.Constant) and isinstance(v.value,str):
                                add(path,v.lineno,v.value,section='literal_user_message')
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr.startswith('qa_') and node.args:
                    v=node.args[0]
                    if isinstance(v,ast.Constant) and isinstance(v.value,str): add(path,v.lineno,v.value,section=node.func.attr)
                if isinstance(node,ast.keyword) and node.arg in ('prompt','message','question'):
                    pairs=[(ast.Constant(node.arg),node.value)]
                for key,value in pairs:
                    if isinstance(key,ast.Constant) and key.value in ('prompt','message','question') and isinstance(value,ast.Constant) and isinstance(value.value,str):
                        add(path,value.lineno,value.value,section='literal_test_input')
    seen={}
    for row in rows:
        row['prompt_mode']='structured' if re.search(r'\b[A-Za-z]+_[A-Za-z0-9_]+\b',row['prompt']) else 'spoken'
        if row['source_status']!='ready': continue
        key=re.sub(r'\s+','',row['prompt']).strip('。！？?!').casefold()
        if row.get('conversation_group'): key+='|'+row['conversation_group']+str(row['turn_index'])
        if key in seen: row.update(source_status='duplicate',duplicate_of=seen[key])
        else: seen[key]=row['case_id']
    return sources,rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--private-output',type=Path,required=True)
    a=p.parse_args(); sources,rows=collect(a.source_root.resolve())
    private=dict(schema='bf.qa.template-inventory.v1',requirement_id='REQ-QA-ALL-LOCAL-TEMPLATES-20260915',
        sources=sources,counts=dict(Counter(r['source_status'] for r in rows)),rows=rows)
    write(a.private_output,private)
    public=json.loads(json.dumps(private))
    for row in public['rows']:
        row.pop('reference_answer',None); row.pop('gold_contract',None)
        row.pop('source_text',None)
        row['prompt']=sanitized(row['prompt']) if row['kind']=='user_prompt' else '[模板正文保留在受控源文件；此项做合同验证]'
        row['public_prompt_is_redacted']=row['prompt'] != next(r['prompt'] for r in rows if r['case_id']==row['case_id'])
        if 'original_expectation' in row: row['original_expectation']=sanitized(row['original_expectation'])
    write(a.output,public)
    print(json.dumps({'counts':private['counts'],'sources':len(sources),'missing':[s['path'] for s in sources if s['status']=='missing']},ensure_ascii=False))
if __name__=='__main__': main()

