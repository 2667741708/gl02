"""Ordinary QA boundaries; no network, database, dynamic code, or process execution.

REQ-QA-NO-CODE-EVIDENCE-BASELINE-20260915
"""
from __future__ import annotations

import re

VERSION = 'qa-evidence-no-code-v8-math-functions'
NO_CODE = '当前暂不提供代码、脚本、SQL 或命令示例，也不执行代码。可以继续用中文步骤、数学计算或已有数据分析来帮助你。'
PROMPT = '''你是“炽穹·高炉炼铁大模型”，面向高炉现场的问答、知识解释和数据分析助手。
直接完整回答用户实际提出的问题。信息充分时直接回答，不为展示能力而调用工具。
允许解释常识与工艺知识、检索已授权文档、做数学计算、分析用户提供的数据，以及分析本轮只读工具返回的已核验事实。
只能声称使用本轮实际获得的来源；没有实时证据时明确说明未核实，用户的假设输入不代表现场测量。
区分已知事实、条件性判断与证据不足。单点或少量假设数据不能确认真实炉况恶化。
炉顶压力受设定值、调压阀及控制动作影响；不能从顶压升降单独推出料柱阻力或透气性好坏。判断透气性须核对压差、风量、料况及同时发生的控制动作，区分受控压力与阻力。
提高风温对焦比、煤比和热状态的影响取决于热平衡、原燃料、富氧及喷煤等条件；相关变化不证明因果，缺少控制条件时不得给出必然方向或生产调节幅度。
未给出正常范围时不能声称波动属于正常；未给出统计检验条件时不能断言有或无统计显著性。
用户问变化时先给出首末变化量，再解释能支持什么结论。不补写未提供的基准、阈值或因果关系。
计算写清输入、公式、结果及总体/样本口径；数学公式允许，不生成任何代码、伪代码、SQL、脚本或命令，也不提出稍后提供或让用户自行运行代码的方案。已有只读查询、统计和界面图表能力继续允许。
不泄露内部实现与凭据；可以解释 MCP 等通用概念。不要转移到用户未问的现场炉况。
MCP提供客户端和服务器交互规范及可实现的授权机制；实际认证、授权、用户同意、隔离和越权防护由具体实现与部署策略负责，不能声称协议本身自动保障安全或自动赋予模型权限。
CV仅在统计输入、单位和比例尺度及有效零点适用时解释；摄氏/华氏温度、非正或接近零的均值不能直接作CV相对波动比较，不通过取均值绝对值或平移数据制造可比较性。标准差与极差仍可描述波动。
正式炉况以有效后台诊断为依据；数据分析不能冒充官方诊断、已验证预测或已执行调控。
优先给出结论和必要依据，篇幅服从问题完整性；不主动追加用户未问的示例问题或工艺算例。代码要求应说明暂时关闭并提供中文替代步骤；混合问题只拒绝代码子任务，其余允许部分继续回答。'''

INTRO = '我是炽穹高炉炼铁助手，可以解释工艺概念和制度文档，完成数学计算，分析你提供的数据，按问题需要查询授权的只读数据，并解释后台诊断及其证据。数据不足时会说明缺项，不把假设当作实测。当前不生成或执行代码，也不写入生产设定值。'
ANALYSIS_PROMPT = '''你是高炉数据分析助手。只依据本轮提供的已核验事实作答。
按问题需要组织“事实、条件性判断、缺项”，完整回答且不输出代码。
只能引用事实中已有的数字并保持原精度，不新增阈值、正常范围、示例数值、调参幅度或数字编号。
明确趋势的时间尺度，首末、回归和近期方向不一致时说明差异；未提供检验不能断言统计显著性。
顶压是受控压力，不能从顶压方向单独推断透气性；核对压差、风量、料况、设定值及调压阀动作。风温与焦比/煤比的关系需要热平衡及原燃料、富氧、喷煤条件，不能把相关性当作因果或直接调控依据。
通用工艺规则本轮未由知识库核实，不冒充已验证预测或正式诊断。缺少阈值和佐证时，只列条件性风险与待核实项。
查询部分成功时先用成功事实回答，不把缺项扩大成所有数据不可用。'''


def snapshot_facts(payload):
    snapshot = payload.get('snapshot') if isinstance(payload, dict) and payload.get('ok') is True else None
    if not isinstance(snapshot, dict) or not snapshot.get('source_time'):
        return ''
    diagnosis = snapshot.get('diagnosis') or {}
    if not isinstance(diagnosis, dict) or not diagnosis.get('main_label'):
        return ''
    labels = {'normal':'正常', 'hot':'偏热', 'cold':'偏冷', 'edge':'边缘发展', 'center':'中心发展'}
    label = labels.get(diagnosis['main_label'], str(diagnosis['main_label']))
    evidence = [str(x.get('text') or '') for x in diagnosis.get('evidence', []) if isinstance(x, dict) and x.get('text')]
    return ('最近保存快照时间：' + str(snapshot['source_time']) + '；快照中的主要判断：' + label + '。\n'
            + '依据：' + ('；'.join(evidence[:5]) or '快照未给出可展开的依据') + '。\n'
            + '来源：授权只读炉况快照。注意：该判断对应上述时间，快照之后的变化尚未核实；不能据此自动调整生产设定值。')


def current_text(question):
    return str(question or '').split('\n[服务端对话状态：', 1)[0]


def code_requested(question):
    text = current_text(question).lower()
    # Negating a code request must not turn ordinary arithmetic into coding.
    text = re.sub(r'(?:不要|不需要|无需|不必|禁止|不)[^，。；;\n]{0,12}(?:代码|程序|脚本|sql|命令|执行|运行)', '', text)
    # Mathematical function nouns are not requests for executable functions.
    # Mask only the noun, preserving explicit code/language/script markers and
    # keeping implementation or execution requests subject to the code gate.
    function_program_request = re.search(
        r'(?:执行|运行|实现|编写|撰写|调试|修复|补全|改写)[^，。；;\n]{0,32}函数'
        r'|函数[^，。；;\n]{0,16}(?:示例|实现|怎么写)', text)
    if not function_program_request:
        text = re.sub(
            r'(?:一次|二次|反比例|对数|指数|三角|幂|数学|分段)函数'
            r'|函数(?=\s*(?:值|图像|表达式|定义域|值域|的(?:斜率|截距|导数|极值|定义域|值域)))'
            r'|函数(?=\s*[fgh]\s*[（(])', '数学对象', text)
    actions = r'(?:写|生成|展示|给出|提供|输出|执行|运行|补全|改写|修改|调试|修复|实现|转换成|翻译成|改成|换成)'
    code = r'(?:代码|伪代码|脚本|sql|命令|程序|python|javascript|powershell|bash|函数|js\b|shell|c\+\+|java\b)'
    return bool(re.search(actions + r'[^，。；;\n]{0,32}' + code, text)
                or re.search(code + r'[^，。；;\n]{0,16}(?:示例|实现|怎么写)', text)
                or re.search(r'```(?:python|sql|javascript|bash|powershell)', text))


def _request_clauses(question):
    text = current_text(question)
    text = re.sub(r'(?:并且|同时|另外|然后|并)(?=\s*(?:写|生成|展示|给出|提供|输出|执行|运行)[^，。；;\n]{0,32}(?:代码|脚本|sql|python|命令))', '；', text, flags=re.I)
    return [part.strip() for part in re.split(r'[，,。；;？?！!\n]+', text) if part.strip()]


def code_request_only(question):
    """Return true when every substantive clause is asking for disabled code."""
    clauses = _request_clauses(question)
    connectors = {'并且', '然后', '另外', '以及', '同时', '再'}
    substantive = [part for part in clauses if part not in connectors]
    return bool(substantive) and all(code_requested(part) for part in substantive)


def apply_request_boundary(question, answer):
    text = enforce_no_code(answer)
    if code_requested(question) and not code_request_only(question):
        if NO_CODE not in text and not ('代码' in text and '关闭' in text):
            text += '\n\n' + NO_CODE
    return text


def boundary_result(question, result):
    if not code_requested(question) or code_request_only(question):
        return result
    out = dict(result or {})
    contract = dict(out.get('completion') or {})
    contract.update(terminal_state='partial', complete=False, policy_limited=True,
                    blocked_subtasks=['code_generation_or_execution'], semantic_review_required=True)
    out['completion'] = contract
    return out


def capability_intro_only(question):
    parts = [x.strip() for x in re.split(r'[，,。；;？?！!\n]+', current_text(question)) if x.strip()]
    allowed = {'你好', '你是谁', '你能做什么', '你能帮我做什么', '你有什么功能', '你都有什么功能',
               '请介绍主要用途', '不需要查询实时数据', '不查现场数据'}
    return bool(parts) and all(p in allowed for p in parts) and any(p.startswith('你') and p != '你好' for p in parts)


def no_live_lookup(question):
    text = current_text(question).lower()
    import qa_task_plan
    return qa_task_plan.lookup_constraints(text)['no_live_lookup'] or capability_intro_only(text)


def direct_result(question, selection=None):
    if code_requested(question) and code_request_only(question):
        return {'ok': True, 'answer': NO_CODE, 'answer_route': 'code_disabled',
                'model_request_count': 0, 'tool_used': False, 'tool_trace': [], 'model_timing': {}}
    if no_live_lookup(question) and (selection or {}).get('mode') == 'required':
        import qa_task_plan
        plan = qa_task_plan.build_task_plan(current_text(question))
        required = (selection or {}).get('tools') or []
        if not required or any(not qa_task_plan.tool_allowed(name, plan) for name in required):
            return {'ok': True, 'answer': '本轮的查询限制与强制工具选择存在冲突。请取消强制工具选择，或明确允许查询的范围。',
                    'answer_route': 'tool_policy_conflict', 'model_request_count': 0,
                    'tool_used': False, 'tool_trace': [], 'model_timing': {}}
    text = current_text(question).strip()
    if capability_intro_only(text):
        return {'ok': True, 'answer': INTRO, 'answer_route': 'capability_intro', 'model_request_count': 0,
                'tool_used': False, 'tool_trace': [], 'model_timing': {}}
    return {}


def enforce_no_code(answer):
    text = str(answer or '')
    # A promise to generate code is a capability violation even without code
    # syntax. Drop only the offering sentence; preserve valid facts/formulas.
    parts = re.split(r'(?<=[。！？!?，,；;\n])', text)
    offering = re.compile(r'(?:生成|提供|给出|输出|展示|编写|撰写|写出|执行|运行)[^。！？!?，,；;\n]{0,60}(?:代码|伪代码|脚本|SQL示例|SQL语句|命令示例|绘图程序|(?:Python|JavaScript|PowerShell|Bash)\s*示例)', re.I)
    negative = re.compile(r'(?:不(?:能|会|再|可|提供|生成|输出)|暂不|禁止|关闭|不支持|无法|避免)[^。！？!?，,；;\n]{0,40}(?:代码|伪代码|脚本|SQL|命令)', re.I)
    kept, offer_removed = [], False
    for part in parts:
        if offering.search(part) and not negative.search(part):
            offer_removed = True
        else:
            kept.append(part)
    if offer_removed:
        text = ''.join(kept).strip().rstrip('，,；;')
        if NO_CODE not in text:
            text = (text + '\n\n' + NO_CODE).strip()
    # Check both ordinary lines and inline examples. Mathematical formulas and
    # quoted sensor names are allowed; executable syntax is not.
    patterns = (
        r'\b(?:def|function)\s+\w+\s*\(',
        r'\b(?:print|exec|eval|console\.log|subprocess\.run|os\.system)\s*\(',
        r'\b(?:const|let|var)\s+\w+\s*=',
        r'\b(?:select\s+.+?\s+from|insert\s+into|update\s+\w+\s+set|delete\s+from|create\s+table|drop\s+table)\b',
        r'(?:^|[\n`;])\s*(?:import\s+\w+|from\s+\w+\s+import|return\s+\w+|for\s+\w+\s+in\s+.+:|while\s+.+:)',
        r'\b(?:Get-ChildItem|Get-Content|Invoke-Expression|Invoke-WebRequest|Start-Process|Remove-Item|Write-Host)\b',
        r'(?:^|[\n`])\s*(?:curl|wget|sudo|chmod|pip\s+install|npm\s+install|rm\s+-|python\s+-c|bash\s+-c)\b',
        r'\$[A-Za-z_]\w*\s*=|=>\s*[{\w]',
    )
    executable_fence_pattern = (
        r'```\s*(?:python|py|sql|javascript|js|typescript|ts|bash|sh|shell|powershell|ps1|java|c|cpp|c\+\+)\b'
        r'.*?```'
    )
    executable_fence = re.search(
        executable_fence_pattern,
        text,
        re.IGNORECASE | re.DOTALL,
    )
    contains_code = executable_fence or any(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in patterns)
    if contains_code:
        safe_text = re.sub(executable_fence_pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
        safe_lines = [
            line for line in safe_text.splitlines()
            if line.strip() and not any(re.search(p, line, re.IGNORECASE) for p in patterns)
        ]
        safe_text = '\n'.join(safe_lines).strip()
        if safe_text and not re.fullmatch(r'(?:代码|示例|实现|脚本|命令)[:：]?', safe_text):
            return f'{safe_text}\n\n{NO_CODE}'
        return NO_CODE
    return text


def broad_hour_analysis(question):
    text = current_text(question)
    return (not no_live_lookup(text) and not code_requested(text)
            and bool(re.search(r'(?:这|近|过去|最近|一|1|两|2).{0,6}小时', text))
            and any(v in text for v in ('风险', '可能出现', '炉况变化', '潜在问题')))
