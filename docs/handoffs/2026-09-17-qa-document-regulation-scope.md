# 条款规程范围、精确层级及逐项覆盖

状态：本机400项与独立静态复核通过，V35-r1候选冻结；生产未应用。
最后核对：2026-09-17。需求：REQ-QA-DOCUMENT-REGULATION-SCOPE-20260917。
关联：QAOPT-K01/K02/K03/K04/K06。权威来源：当前代码、隔离原生PG回归、私有实际原源读取验证。
适用边界：确定性文档选择及覆盖状态，不代表全部口语或线上准确率已通过。

## 逐项问题及处理

1. 用户限定安全规程时，其他规程同句可能被引用。现在先过滤规程再匹配排序，错误规程精确命中不能覆盖指定规程的前缀命中。
2. “不要引用某规程”被当成要求引用。现在分别维护肯定与排除范围；直接矛盾返回regulation_scope_conflict澄清。
3. 原句引号内的岗位或规程词被误解为查询范围。现在所引条款字面内容与外部范围分开解析；制度岗位名也不自动成为额外规程请求。
4. 层级路径1/1.1包含匹配11/11.1。现在拆解各级并精确比较编号，再核对标题。
5. 多种规程仅回答其中一种却标为完成。现在按岗位和请求规程逐项检查；缺项写入missing_regulations_by_chapter，保留现有原文并标partial。
6. 原子条款中某一规程缺失或歧义时，另一已唯一确认结果被丢弃。现在有唯一结果则返回原文并列出missing_regulations/ambiguous_regulations；完全没有唯一结果才needs_clarification。
7. 多个完整条款超过单页时没有一致分页。现在整块分页并保留完整表格，coverage分别列出总匹配与当前页返回数；多页单次读取始终partial，越界页澄清。

实现：[字面范围](../../高炉前端数据/智能助手/backend/qa_document_knowledge.py:120)、[规程解析](../../高炉前端数据/智能助手/backend/qa_document_knowledge.py:207)、[覆盖门](../../高炉前端数据/智能助手/backend/qa_document_knowledge.py:258)、[原子条款](../../高炉前端数据/智能助手/backend/qa_document_knowledge.py:280)、[公开入口](../../高炉前端数据/智能助手/backend/qa_document_knowledge.py:575)。
固定原源binding、release、全量after和单MVCC SELECT核验继续保留；不引入模型调用、源缓存、HTTP路由或DDL变化。

## 验证与分母

- 新回归初19项在V34实际17fail/2pass；后续中间候选另3分页项2fail/1pass。不同版本运行分别记录，不合并成虚构初始准确率。
- 修复后13模块合并400 passed，34.85秒；随后仅给测试增加全结果严格JSON序列化断言，22项再次通过，5.92秒，运行代码未变。
- 隔离原生PostgreSQL16.13及真实public.vector；实际固定r2原源5587索引、11组、14次读取保真再次通过，15.07秒，投影常量未替换。
- 独立gpt-5.6-luna low初审遗漏not-chosen guard而FAIL；要求重读完整控制流后纠正为PASS。没有为绕过审查删断言或改变完成标准。
- 0生产请求、0模型调用、0数据库生产写入。全部检查为本机隔离验证，不推导822题线上准确率。原文、原问题、答案与私有PG数据不上传。

命令、代码摘要、分母与界限：[机器证据](../../tests/qa_regression/document_regulation_scope_20260917.json)。

## 候选与固定底座

私有V35-r1含10个Python文件及manifest；manifest SHA256 a5fa56111d7b4ff85bd222a6d8dc63002dd73a0425cf8252a2123cfa58afc4af。
读取器SHA256 6ae781baf848f85a7d4fc18e64a0485a586bc75e21e926c44d5951b7c1bdad7a；其余9个文件与V34逐字节相同，AST解析/本候选模块导入通过。
本机冻结不等于生产密封，read_set仍须在线重核。

固定chiqiongblastfuenace:latest及e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124；禁止模型切换、fallback及同名权重替换，身份不一致停止调用。
代码执行及代码示例继续禁用，普通推理和数据分析保留。审查用Codex模型与生产助手底座是不同任务，此次审查不调用或更换助手底座。

## 生产与剩余工作

本轮Reliable SSH身份及显式路线探测超时，无生产命令派发，不能推断服务器故障或模型驻留健康。生产V26仅为历史快照；V27—V35仍未部署。
管理器/恢复任务安装与源DB迁移/发布/回滚各自授权尚待落实；8093代码部署授权不能扩大为其他服务或数据库操作。
连接恢复后先只读核实r3进度/进程、生产版本/hash、固定模型身份、实例/config/read_set，依受控闭环发布，不接受不同digest成为新基线。

33项台账状态保持，本轮0销项；K04保留V34重新deployed_partial_verified及旧生产证据。
部署完成后串行复问822原失败/partial题，每题单次POST，未知发送TPL-10C8C8FAF2C694EF禁止重放；按原ID和原裁判分别统计传输、语义与成功回答率。
本轮822题0复问；30标准冲突、89oracle阻断、topic完整性与复杂自然语言关联继续单列。

[V34交接](2026-09-17-qa-document-scope-resolution.md)及早期测试作为历史阶段保留。修复目标尚未完成。
