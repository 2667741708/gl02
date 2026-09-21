# keyword制度源受控执行入口

状态：本机291项及独立静态复审通过，私有entry-r1包冻结；生产未执行。
最后核对：2026-09-17。需求：REQ-QA-SOURCE-RELEASE-ENTRY-20260917，关联QAOPT-K03/K06。
权威来源：真实隔离原生PG测试、Reliable SSH只读实例/配置核验、私有封存包及静态审查。
适用边界：source-only连接/发布/回滚/恢复入口；不创建迁移表，不运行模型，不代表生产数据库已更新。

## 实际实现

1. [执行入口](../../tools/qa_keyword_source_release_entry.py)提供plan/publish/rollback/recover；契约字节SHA绑定精确action/operation_id、root、主机指纹、数据库实例指纹、service配置hash、keyword和同一模型名称/权重摘要。实例指纹包含真实system_identifier/库/role/地址/端口/PG主版本/schema/非备机状态，原身份仅私有，公开不上传。
2. plan仅核输入与目标契约，0连接/配置秘密读取/执行记录/模型调用。其他操作先核配置hash、显式keyword与schema，从连接启动即只读核验数据库实例；write动作在核验后通过同一owned连接的read_only属性进入新事务。绕过连接池和schema初始化。
3. publish/rollback必须单独获得生产数据库授权；CLI标志或源码中的authorized参数不能代替用户授权。尝试使用O_EXCL独占执行编号，fsync保存claim，再核identity/write_started/result。重复编号在第二次连接前阻断，崩溃/提交/收据不确定均不自动重放。
4. recover仍启动只读，经相同实例核验后调用已有REPEATABLE READ恢复；不写执行记录或源数据。缺journal保持unresolved。异常只返回稳定错误码，finally回滚/关闭连接并恢复PG环境；不输出连接参数或数据库原行。
5. root/config/执行记录目录拒绝symlink与Windows reparse point。contract/candidate/manifest/plan输入有限字节，固定r2计划及5587行保持。
6. service配置中keyword必须显式存在；即使配置hash重新封存，缺失/None/hybrid仍在数据库连接前阻断，不假定缺配置时keyword生效。

## 实际验证

[入口20项测试](../../tests/test_qa_keyword_source_release_entry.py)使用既有隔离原生PostgreSQL16.13/真实pgvector夹具，不修改生产constants。
真实system_identifier等聚合指纹核验后完成发布→只读恢复→完整回滚→只读恢复；相邻文档/向量不变。
测试还覆盖plan无连接/读secret/写记录、未授权、固定模型/keyword/计划/主机/root/未知字段拒绝、错误contract SHA、同编号无第二次连接、实际DB身份不符、config漂移、DELETE后的事务失败、提交成功但收据I/O失败及显式keyword三个反例。
合并18项事务及253项源/绑定/只读回归实际291 passed（16.81秒），独立静态复审PASS。入口及封存副本--help通过。命令与实际hash见[脱敏机器证据](../../tests/qa_regression/source_release_entry_20260917.json)。

本轮Reliable SSH只读确认r3完成953/953、PID18224退出、8093仍V26 HEAD7d8a2b1及proxy SHA47b7e75…f431。源连接从启动起default/current只读均on，数据库实例聚合指纹和显式keyword实际核验；未输出原身份/配置秘密。

## 私有封存候选与执行顺序

entry-r1仅位于Git忽略目录.codex_runtime/qa-source-scope-20260917/entry-r1；12文件包括三个源artifacts、三个Python闭包文件、增量DDL、四个action契约及package manifest。固定r2原plan，不改历史冻结产物。
manifest SHA256 b692938771b2b0e1b8836ed4d5a3c2e3d321c61e1406c65275226fb5ddffd3df。私有manifest记录精确生产assistant_pg.py只读依赖hash；执行前主任务必须重新核验全部封存文件、该read_set、目标配置/身份/源基线，不能让同名文件漂移。
封存与构建0数据库连接/模型调用/生产写入，不上传到GitHub；全包重放不作为失败恢复方法。

生产执行须分阶段：取得数据库单独授权→重新只读核查→upload-only临时预暂存→核完整manifest/read_set/实例→独立受控增量DDL阶段→完整schema验收→一次publish→新只读连接核release/after快照→接入读取门禁及守卫8093发布。
增量DDL候选未执行，入口不代为创建表。任何DDL/数据commit或SSH状态不确定先只读恢复，不自动重放。回滚另用绑定该实例、release及精确after的已审查契约，保留新增表与审计。

## 未完成项

生产数据库修改授权尚未收到；迁移/实际发布/旧向量归档和现场回滚均未执行，读取器尚未接入。固定模型管理器与恢复任务安装继续保持单独授权边界，模型名及e4ad74…d8124权重不可变，不切备用模型以推进。
QAOPT-K03/K06保持deployed_partial_verified，本轮0问题销项；822原失败/partial题本轮修复后0次发送，优化后准确率不可报告。30项源/标准冲突、89项oracle阻断、topic完整性及答案语义继续单列。
上一[271项事务交接](2026-09-17-qa-keyword-source-transaction.md)为当时阶段快照；当前入口状态以本交接为准。
