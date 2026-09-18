# QA V5生产验收与V6剩余修复

- 状态：V5已部署并完成八题语义审查；V6本机候选，尚未部署。
- 最后核对：2026-09-16；需求：REQ-QA-FULL-ISSUE-INVENTORY-20260916。
- 权威审查：[V5结构化结果](../../tests/qa_regression/routing_v5_production_review_20260916.json)；长期台账：[逐项台账](../../tests/qa_regression/optimization_execution_ledger_20260916.md)。

## 已部署V5

受控执行`qa-routing-v5-20260916-r1`成功，8093 PID 15520→2956，HTTP200，七文件安装哈希通过，守卫finally恢复，无回滚。8094/8768/8770/5432/11434 PID保持16576/6440/844/12372/6732，没有修改其服务或配置。

生产提交`312085a88ae95027728d5b8b72c4293af834d055`；版本ref`refs/prod-8093/20260916/qa-routing-v5-20260916-r1`。CAS一次成功，仅记录已验收七目标，保留无关索引。激活46523.455ms，版本记录2799.464ms，同一受保护SSH连接复用。

八题各发送一次，无自动POST重试。七题有落盘的SSE done；首题返回后复测器因缺expected字段异常，原事件未落盘，只读GET按精确问题和请求时间恢复一条数据库答案，不重发，不补造事件证据。已修复复测器在发送前补齐元数据并增加结果保全回归。一次健康状态阻断发生在第六个未发送题之前，证明无claim后才续跑该题。

语义结果：2通过、4部分、2失败。相邻窗口差值及日报摘要通过。历史owner隔离和预取兄弟模块导入已修复，但历史摘录自我递归、温差分析完整度、无工具截断及无证据参数匹配仍开放。bounded GET就绪重查不能保证其他端口共享Ollama时的跨进程驻留租约。

## V6本机候选

1. QAOPT-R02：SQL在LIMIT前排除历史检索自身生成的答案；明确要求回答时只匹配assistant。保留owner与当前消息ID截止，通配符转义不变。
2. QAOPT-E02/E04/E05/E06、R03：EvidenceItem固定对象/采集时间/来源/单位。单点预取直接展示事实与限制，不自由推断正常、匹配、趋势或因果。四点温差说明窗口均值与同时刻空间温差的区别，检查缺点、重复、时间窗、有限数值、样本覆盖、全零和单位；缺失不填零，不编造异常阈值。
3. QAOPT-R07/E05：JSON与SSE无工具路径检测Ollama长度终止，同一用户请求内最多一次压缩补答；仍截断或失败保留partial并提示，没有外部POST重放。完成元数据不等于语义通过。
4. QAOPT-R10：显式短追问才继承对象/时间；新主题、禁实时、工艺解释或超过十分钟状态清除继承。上一轮实际数值证据不复用，保留可核对继承原因。
5. QAOPT-O04：修复SSE准备完成日志处于except-return后的不可达缩进；最终响应附独立completion状态。

构建器只对精确V5生产字节补丁，禁止部署已跟踪旧代理。最终106项聚焦回归通过，含复测器落盘保全与异常来源形状；发布审查PASS。远端Python3.11只编译通过，十二依赖哈希一致、读写范围无已有改动；临时索引原始/语义275行一致，没有换行迁移。无前端或其他端口修改。

## 复现与后续验收

`python -X utf8 tools/build_qa_routing_v6_candidate.py --v5-candidate .codex_runtime/qa-routing-v5/candidate --output .codex_runtime/qa-routing-v6/candidate`

`python -X utf8 -m pytest tests/test_qa_history_projection.py tests/test_qa_v6_contracts.py tests/test_qa_retest_persistence.py tests/test_qa_retest_readiness.py -q`

后续先密封、生产只读基线/哈希复核、Python3.11编译与临时索引记录门、审查，再受控8093切换，真实单次复测并语义核查。833知识题单列，828尚待语义审查；其余台账不因候选代码或非空答案标记全通过。
