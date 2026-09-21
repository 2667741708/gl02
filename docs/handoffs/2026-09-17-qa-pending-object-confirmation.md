# 测点确认接续和准备阶段权限顺序

状态：V50-r3本机冻结候选；36模块975回归、55服务器原生只读合成合同和独立审查通过，尚未部署和复测原失败题。
最后核对：2026-09-17。需求：REQ-QA-PENDING-OBJECT-CONFIRMATION-20260917；关联QAOPT-R01/R07/R08/R10/O01/T05。
权威：冻结V49-r6/V50-r3、实际owner加载与prepare/JSON/SSE流程、Reliable SSH原生Python3.11.9 RAM探针及gpt-5.6-luna有界独立审查。范围：8093智能助手代码；不授权模型、恢复任务、知识数据库和其他服务修改。

## 实际问题和修复

助手问“哪个测点”之后，用户回复“总压差”，现有上下文更新会丢失此前分析目标和时间窗。新增服务端待确认任务只保存目标、相对窗口、图形和原时间戳；不保存模型推测、原始问题或数据值。只能从归属当前owner的已持久化用户消息加载；有效期600秒，未来时间、legacy、错误类型、非法目标、窗口或图形一律拒绝继承。

确认要求整句精确匹配既有测点目录，允许有限确认前缀、引号和对象分隔符。不以模糊匹配、额外动作或客户端拼接状态创建授权。有效确认保留目标和窗口，在当前用户消息重新绑定对象，重新取数。相关性只有一个测点时继续澄清，原有效期不延长。缺少有效待确认任务的裸测点不自动成为现场查询，先澄清目标和窗口。

首轮原生检查发现：即使纯函数回归通过，prepare仍会在owner确认之前执行6次通用传感器读取；过期及其他会话的确认也可能默认预取。修复将owner加载和待确认解析提前到任何传感器读取之前；有效确认同样不注入通用传感器上下文，只执行后续精确测点查询。过期或无法核验归属时关闭预取、MCP、知识和来源域。原问题文本保持不变，内部查询文本不替换用户消息。

页面选择禁用工具时，早期传感器策略和后续任务计划都收敛权限，不能因重建TaskPlan恢复读取。仅用户数据、原文、聊天历史、报表、规则解释、新话题和纯代码请求不借此获得现场权限。代码执行和代码示例仍禁用。

## 冻结和可复现验证

V50-r3 manifest SHA256 `0b30d0f39df03eeee14e9660252398454f434d8e233fea13850a11aecf23c8d0`。16文件中14个逐字节继承V49；planner移除两个新增纯函数及math导入后，原有AST完全一致；proxy只修改prepare_qa_chat，恢复该函数后其余全AST一致。固定模型模块及V47共享ABC实现和两个依赖pin保持。

服务器Python3.11.9 RAM加载16候选模块及60实际只读依赖。10问答Handler、6普通准备、15原有追问、15测点确认和9共享ABC共55合成合同通过。有效确认允许1次模拟精确预取，失效/澄清/禁工具为0；所有确认零通用传感器读取、零模型请求。JSON/SSE两轮夹具实际执行首轮do_POST生成待确认状态，再运行确认prepare；检查原问题、当前来源ID及页面归档与证据隔离。

外部数据库、鉴权会话、传感器提供者、模型传输、MCP预取和线程仍为明确模拟；真实取数、最终模型答案和并发没有验收。不得把55合同或本机测试数解释为生产回答准确率。初轮11个新增合同失败、第二轮2个失效窗口预期错误及AST隔离夹具缺少原模块别名常量的24项失败均保留私有记录，未计入原题错误统计。

```powershell
python -B -X utf8 tools/build_qa_pending_object_candidate.py --revision rN
python -B -X utf8 -m pytest -q tests/test_qa_pending_object_confirmation.py tests/test_qa_pending_confirmation_evidence.py tests/test_qa_sensor_context_source_gate.py tests/test_qa_ordinary_context_source_gate.py --basetemp=.codex_runtime/qa-pending-reproduce-new
python -B -X utf8 tools/evaluate_mcp_gold_tasks.py --validate
```

rN和basetemp必须为新编号/目录，不覆盖既有候选或收据。严格原生验证器要求完整15项确认、无遗漏重复，并拒绝隐藏传感器读取、失效预取、旧窗口、未绑定当前消息及未由首轮Handler生成的待确认状态。完整本机回归命令和耗时以[脱敏机器证据](../../tests/qa_regression/pending_object_confirmation_20260917.json)为准。

## 生产更新分类和剩余门

已只读核对Git日志：e3cca54仅修改ABC33说明样式；cdd390共享proxy改动已经继承到候选。助手16目标/60依赖范围不与最新CSS更新相交；保留无关生产提交和既有无关改动，按[路径范围部署门](2026-09-17-qa-deployment-path-scope.md)继续准备，不能仅因全仓HEAD不同拒绝更新。

固定底座仍要求`chiqiongblastfuenace:latest`、digest `e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124`，不切换、不回退、不替换同名权重。13:31:44 UTC两次tags是e4，但ps全部驻留记录是9111；13:54:27 UTC两次tags和ps全部为9111。两个快照分别记录，不能合并成持续健康或推定执行者。主任务0模型操作、0原题POST、0生产写入。禁切换管理器与恢复任务的独立授权仍待回应；没有自行扩张8093权限。

所有33项仍待生产闭环，822原失败/部分题范围保持。完成本机、范围、密封、固定底座及受控8093验收后，才单次复问原失败题并独立审阅完整最终答案；未知发送不自动重放。
