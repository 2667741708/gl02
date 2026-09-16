# QA V5 本机候选

- 状态：本机验证通过，生产未切换。
- 最后核对：2026-09-16。
- 需求：REQ-QA-FULL-ISSUE-INVENTORY-20260916。
- 权威来源：精确V4候选哈希、V4线上审阅、本轮测试。
- 边界：8093代理/确定性辅助模块及该服务独立MCP副本；无模型、数据库结构或其他服务配置变更。

## 逐项修复

|问题|修改|本机验证|生产验收|
|---|---|---|---|
|R03|带当前/窗口锚点的观测式大不大等问句进入数据域；通用原因/原理与禁实时指令继续跳过|TaskPlan冻结四个炉喉点并打开工具门|待复测A-D|
|R04/E04|按真实query_gl02_sensors扁平items取统计，兼容旧包装；对象、窗口、来源和样本校验不变|执行真实MCP函数AST产生扁平结构，再独立计算两窗差值；错对象仍失败|待复测两窗|
|R05|识别摘要元数据行；无摘要时返回summary_missing，不回退正文明细；截断仍显式标记|合成日报元数据、明细分离及缺摘要终态|待复测日报|
|R02/O05|SQL绑定已认证owner和当前message ID；只读提取之前的消息；历史原始JSON及代码不展开|真实SQLite两个owner、通配符转义、排除当前题；实际JSON/SSE代理接缝验证|待复测历史问答|
|R02/K02/K05|无身份范围的旧MCP历史函数返回QA_HISTORY_SCOPE_REQUIRED；历史消息不作为实时或正式制度证据|真实生产函数AST不具备数据库访问路径|待运行及角色验收|
|E01|动态导入MCP时加入已验证的同目录依赖路径，并锁住首次导入|真实临时Python同目录依赖加载一次且复用实例|待验证预取|
|O01|允许驻留清单下有限GET复核；去掉重复模型解析及健康检查中的show元数据读取|失驻留、非允许模型、期限、取消均覆盖；状态只访问version和ps|待复测；外部服务仍可能变更驻留，不能宣称跨服务租约|
|O01/O04|模型依赖阻断输出code/retryable/terminal_state和automatic_replay=false|辅助模块及接缝验证|待故障验收|

## 验证

103项聚焦pytest通过；TaskPlan合同15/15；MCP金标结构14/14（结构通过不等于语义通过）。
发布脚本通过PowerShell7解析与UTF8验证。候选基于已接受V4提交
`f79b13ccf79d3b522c5a7a253989c9915df74aa4`，仅七个精确文件；读集包含不变实体解析器和同目录catalog。

```powershell
python tools/build_qa_routing_v5_candidate.py --v4-candidate .codex_runtime/qa-routing-v4/candidate --output .codex_runtime/qa-routing-v5/candidate
python -m pytest tests/test_qa_routing_v5_candidate.py tests/test_qa_history_projection.py tests/test_qa_model_readiness.py -q --basetemp .codex_runtime/qa-routing-v5/pytest-review
```

## 未完成范围

33项台账仍执行中；828条知识回答尚未完成全部人工语义审阅。
复合历史+现场问题中的旧MCP历史调用会明确失败，不绕过身份门。
历史已污染的共享消息本轮不做数据库删除；不能用本次入口修复声称撤回既有内容。
代码执行及代码示例生成继续禁用。新答案的非空和SSE done不单独作为通过标准。
