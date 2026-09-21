# keyword制度源发布、精确回滚与提交恢复事务

状态：本机事务库、271项测试及独立静态复审通过；生产未应用。
最后核对：2026-09-17。需求：REQ-QA-KEYWORD-SOURCE-TRANSACTION-20260917，关联QAOPT-K03/K06。
权威来源：实际原生PostgreSQL隔离测试、Reliable SSH生产只读依赖核查、固定r2计划及独立静态复审。
适用边界：新连接事务库；尚无生产操作入口，未取得数据库修改单独授权，不代表读取器接入或答案语义通过。

## 固定底座强约束

唯一模型名称chiqiongblastfuenace:latest，唯一权重SHA256 e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124。
禁止换名称、版本切换、备用底座回退、同名权重替换；任何身份漂移均阻断模型调用与配对复测。不得接受生产漂移作为新的基线。
本事务库不执行模型操作或生成embedding；发布计划固定同一摘要。既有[固定底座运行时候选和管理器](2026-09-17-qa-single-base-model-policy.md)尚未安装，不能声称生产已锁定。

## 已实现的事务合同

1. [事务库](../../tools/qa_keyword_source_transaction.py)只接受调用者持有的全新非自动提交连接；写入必须明确authorized=true，参数不能代替用户生产数据库授权。固定计划字节SHA及candidate/manifest，不连接数据库、不持有凭据、不自动运行。
2. 非阻塞advisory事务锁；完整schema检查前取得五张目标表SHARE ROW EXCLUSIVE NOWAIT锁，允许普通SELECT，阻止其他写入及元数据改动。完整校验实际列类型、主键、所有传入/传出外键、用户触发器及真实public.vector；未知级联依赖写入前阻断。
3. 锁内校验旧版本、完整文本hash、chunk分类及embedding计数、跨文档ID冲突。同事务归档旧11/21/6字段集合、search_text、实际vector文本及先前绑定，不输出归档正文。
4. 保留rag_document身份及来源/创建时间，仅替换精确doc_id的索引/向量/来源绑定。新keyword版本不生成向量；旧向量仅归档用于精确回滚。
5. 同事务校验完整after快照hash及全部实际检索字段后commit。失败回滚；commit异常无论是否已生效均标记不确定，禁止自动重放。
6. rollback_release仅在发布身份与精确after快照一致、旧归档hash/基线正确且旧ID未被其他文档占用时，恢复全部旧行、vector值及先前绑定，并保留发布审计。
7. recover_release使用启动即只读的新连接及REPEATABLE READ，验证发布状态、before归档、旧基线及当前state对应快照。无journal仍是not_recorded_unresolved，不授权重试。所有异常只输出稳定错误码，finally回滚失败单独报未核实。
8. [只读依赖探针](../../tools/probe_qa_keyword_source_dependencies_readonly.py)使用既有启动只读连接，仅读目录元数据，不初始化schema。

## 实际验证及边界

[原生PG测试](../../tests/test_qa_keyword_source_transaction.py)和[合成SQL夹具](../../tests/qa_regression/keyword_source_pg_fixture.sql)在Git忽略目录建立独立localhost PostgreSQL16.13及真实pgvector，每次核对精确data_directory与测试role；不使用生产连接，不降级为假vector。
18项事务测试覆盖发布/完整回滚、其他文档不变、重复发布、DELETE后失败回滚、提交已生效/未生效两种不确定状态、快照/归档/基线漂移、新旧ID跨文档冲突、锁竞争、缺迁移、未知外键/触发器、只读恢复要求、未授权/非空事务及元数据锁并发DDL阻断。
合并253项既有源/绑定/只读回归后实际271 passed，49.28秒。独立静态复审PASS，无数据库连接或远端操作。复现命令见[机器证据](../../tests/qa_regression/keyword_source_transaction_20260917.json)。

首次隔离测试启动夹具曾因Windows守护进程继承管道阻塞及含中文data_directory的原生GUC编码报错；仅停止已核实临时实例，改用普通输出文件及该元数据列的局部raw-text loader后通过。原文和正常SQL结果仍UTF-8；这些夹具错误不计线上问答失败。
本轮Reliable SSH只读确认现有源表两条CASCADE外键、无启用用户触发器、embedding为public.vector。r3仍953/953完成，初始PID18224已退出；8093仍V26 HEAD7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e及proxy SHA47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431。
0生产数据库写入、0模型/问题POST、0语义销项。历史[253项准备报告](2026-09-17-qa-keyword-source-release-preparation.md)保持当时快照，不覆盖其“执行器未实现”标记；当前实现状态以本交接为准。

## 尚未完成

受控生产操作入口及目标实例身份/持久化不重放记录、数据库修改单独授权、增量DDL及实际发布/回滚验收、完整章节/表格读取器接入仍待完成。旧计划及源候选继续固定r2，不修改原题或评分。
固定底座管理器/恢复任务安装仍需其单独授权，8093部署遵守守卫流程；本轮未申请扩大操作范围。
822原失败/partial题在本轮修复后0次复问，无法报告优化后准确率。30项知识标准冲突、89题oracle阻断及topic完整性/答案语义单列。
