# V28统计证据修复与固定底座保留

状态：本机候选；尚未部署，线上语义效果未验证。
最后核对：2026-09-17。需求：REQ-QA-STATISTICS-EVIDENCE-20260917；关联QAOPT-E01/E02/E03/E04/E05。
权威来源：V24冻结答案审阅、V27冻结候选、实际函数隔离回归、Reliable SSH只读检查及独立审查。
适用边界：普通问答统计预取和确定性工具答复；不修改ABC33首问或高炉设定值。

## 已记录问题与修复

|问题|最小修改|核对方式|
|---|---|---|
|预取摘录丢弃stddev、单位、质量及未来统计字段|完整深拷贝statistics、variable元数据、source和实际/请求时间窗，保留旧消费者平铺字段|实际qa_mcp_prefetch函数的合成只读工具夹具；原实现缺stddev/unit，新实现保留|
|count=0或空first对象误判为完整证据|要求正整数样本数、有限数值、对象匹配、来源和窗口绑定|旧函数可复现误判，新函数拒绝|
|极小非零变化舍入成0或-0，但仍描述方向|普通数值保留三位显示；会舍入为0的非零值用有效数字表达；非有限数、布尔值、字符串不作为数值事实|实际确定性答复前后对照与数值反例|
|缺单位自动补齐却不披露|仅现有精确GL02单位合同可继承并披露原字段缺失、未换算；未知对象保留单位未核实|已登记/未登记单位及原始Pa不转为kPa|
|Held端点被忽略|显示首末质量，说明端点不代表整窗质量；Held不能证明新增实测或炉况稳定|显式质量及恶意未知标签反例|
|直接工具答复绕过预取证据校验|精确绑定规范ID或元数据别名、外层请求variables及请求窗口，再复用同一证据门；无有效证据跳过正式STDDEV/CV/趋势|缺来源、写策略、错对象、错窗口、缺外层绑定、参数覆盖反例|

本轮来源案例仅公开稳定ID：TPL-01EEE414179DB624、TPL-FACD6F5FE05C74FC、TPL-BE97AA4EAD567003。原始会话和生产测量值未进入公开产物。

## 同一底座强约束

唯一digest仍为`e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`，业务别名`chiqiongblastfuenace:latest`。V28由冻结V27构建，仅修改qa_mcp_prefetch、qa_mcp_prefetch_is_complete、deterministic_mcp_answer；其他AST保持一致，固定身份三个函数及固定身份模块不变。任何模型回合均不得切换或备用模型兜底。

r4代理SHA256：`bc815f53bb5242b762eaf6d5071bf8cf6481a1ecdf356884026e8b2a5108cfd3`。
统计模块SHA256：`67c3dd0ea45122935ca3fb88f9446cd68225d099d0f6285d1c751cf8da8482be`。
固定身份模块SHA256：`e1251801bb9e4e1eb29e78ee138b34ba3bea95b68b46a95f0f960d65ded48c1d`。
生产只读HEAD仍为`7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e`，代理SHA256仍为V26的`47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431`，旧管理器SHA256仍为`856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa`。
本轮最新只读GET中alias和唯一实际驻留均是固定digest；这只是瞬时状态，旧Recovery管理器仍存在，不能声称生产禁切换已经完成。

## 回归和审查

回归入口：[test_qa_statistics_evidence.py](../../tests/test_qa_statistics_evidence.py)、[test_qa_statistical_scope.py](../../tests/test_qa_statistical_scope.py)、[test_qa_latest_reuse_and_code_offers.py](../../tests/test_qa_latest_reuse_and_code_offers.py)。核心32题和旧MCP金标没有被替换。

```powershell
python tools/build_qa_v28_statistics_candidate.py
python -m pytest tests/test_qa_statistics_evidence.py tests/test_qa_statistical_scope.py tests/test_qa_latest_reuse_and_code_offers.py -q --basetemp .codex_runtime/qa-single-base-model-20260917/pytest-statistics-fresh
python tools/evaluate_mcp_gold_tasks.py --validate
```

构建器拒绝覆盖已有冻结候选；需要重新构建时先审查并选择新的私有输出目录，不删除旧候选。pytest的basetemp应使用新子目录。r3实际92项通过；r4最终检查结果以[机器证据](../../tests/qa_regression/statistical_evidence_candidate_20260917.json)为准。旧金标校验实际14题0错误；它验证合同，不是线上回答通过。
独立gpt-5.6-luna low审查r3发现直接渲染绕过并FAIL；修复后r4审查PASS。不得隐藏前一次缺陷，或将审查PASS等同于生产准确率提升。

## 未完成项与下一步

- 未登记温度及上下压差单位仍保持缺项；不根据变量名称猜测单位。
- 整窗Held/Bad数量及采样覆盖率仍需工具提供真实质量统计；目前只披露端点局限。
- 直接跨变量比较、制度阈值及正式风险/稳定等级不能仅凭描述性统计确定，继续按原台账逐项验证。
- 最終回答截断和任务覆盖问题尚未因本轮统计修复全部解决。
- 禁切换管理器安装及Recovery暂停/恢复仍等待单独计划任务授权；不在本轮本机修复中修改生产任务或模型。
- 固定底座身份和受控8093发布验收满足后，才发送新密封计划内822原失败/部分题；原发送状态不确定题禁止重放。
- 第一次1233有效题的636失败、186部分、142不可评分分类保持原口径；本轮没有新增线上答案或优化后准确率。
