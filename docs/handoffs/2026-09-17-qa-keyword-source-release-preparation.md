# 智能助手keyword制度源发布准备及绑定门禁

状态：本机发布计划r2冻结、253项回归及独立审查通过；发布/回滚执行器尚未实现，生产未更新。
最后核对：2026-09-17。需求：REQ-QA-KEYWORD-SOURCE-RELEASE-20260917，关联QAOPT-K03/K06。
权威来源：Reliable SSH启动只读连接的真实表结构/旧源核查、冻结源候选、实际合并测试及独立审查。
适用边界：发布准备及纯源绑定；不代表数据库快照已保存、迁移执行、读取器接入或答案语义通过。

## 本轮实际实现

1. [纯绑定门禁](../../高炉前端数据/智能助手/backend/qa_knowledge_source_binding.py)固定原DOCX、manifest、candidate和authority SHA，不建立连接、不加载模型。拒绝重复JSON字段、非有限JSON、超大字节、错误身份、不完整/重复/污染chunk集合及源内容/元数据漂移。
2. 统一keyword行投影，核对实际RAG字段的值及类型：标题、summary、关键词、实体、类别、任务范围、priority、search_text等均按固定候选绑定；不能只以正文及content_hash互证。
3. 实际数据库没有chapter_code/regulation_type/chapter_title/source_block_start/end专列，岗位/规程头由enriched_content和源manifest绑定。如调用者额外传入解析后的源元数据，也必须与固定candidate一致。不能编造数据库列。
4. `verify_database_source`强制固定candidate字节与manifest，并要求document/chunk的非空source_file一致；调用者须从同一一致性事务快照取得文档和完整索引。
5. `verify_prepared_source`单独核对规划行，明确`database_snapshot_verified=false`；未填充旧source_file的规划不能冒充真实DB验收。
6. [私有准备器](../../tools/prepare_qa_keyword_source_release.py)限定正式doc_id与旧版本/CAS、输出到全新Git忽略目录，生成5587行keyword私有计划。保留source_file/文档created_at政策，归档/锁/验收/提交不确定/回滚步骤写入计划，不执行它们。
7. [增量DDL候选](../../schema/20260917_qa_keyword_source_release.sql)仅新增来源发布归档及绑定表，存放受控数据库中的旧文档、完整索引、向量及先前绑定。尚未执行；部署前必须核对已有表/约束，IF NOT EXISTS不作为已有schema正确性的证明。

## 真实生产只读证据

旧文档仍`v1.0-hierarchical`，content_hash与canonical全文hash均`96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e`。
4540 atomic、805 topic、109 section，共5454 chunk及5454 embedding。rag_chunk_embedding.embedding实际为vector；外键是doc→chunk→embedding的ON DELETE CASCADE。该证据仅为源结构，不输出原文、source_file或连接参数。
8093仍V26 HEAD `7d8a2b1a73fbd3e5b30cf800135ec32c3fa5548e`，proxy SHA `47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431`；r3已953/953完成，初始PID18224不存在。本轮0数据库写入、0模型POST、0问题POST。

## 冻结与实际验证

私有r2：`.codex_runtime/qa-source-scope-20260917/keyword-release-r2`，release_id `qa-source-keyword-20260917-r2`。
plan SHA256：`7ca28451af71cc389076bba21774f75540597a4e926ed4e0a0bf9280dd7dd16d`。
源manifest/candidate沿用[独立源范围候选](2026-09-17-qa-independent-source-scope.md)的固定hash；规划行4663 atomic、803 topic、121 section，5587行全部通过准备绑定，topic完整性及语义仍未验证。

```text
python -m pytest -q --basetemp=.codex_runtime/qa-keyword-source-release-20260917-r2 tests/test_qa_knowledge_source_binding.py tests/test_qa_source_candidate_freeze.py tests/test_qa_source_scope_contract.py tests/test_three_rules_heading_boundaries.py tests/test_qa_readonly_pg.py tests/test_qa_document_integrity.py tests/test_qa_document_knowledge.py
```

实际253 passed（1.49秒），其中本轮绑定/准备51项。独立审查初次FAIL指出DB分支未完整校验源/检索元数据；结合实际表结构补齐确定性元数据和可选源属性绑定、来源路径及准备/DB入口区分后复核PASS。r1保留且不发布，不覆盖历史结果。公开[脱敏机器证据](../../tests/qa_regression/keyword_source_release_preparation_20260917.json)不含原文或私有计划。

## 待实现的受控发布事务

以下为执行器必须满足的合同，尚未执行或全部实现，不能因为计划冻结就声明可回滚：

1. 取得数据库修改单独授权，验证实例、schema和增量表合同。使用主任务持有的新连接；非阻塞doc advisory lock及有限锁等待，锁定文档、目标chunk/embedding及来源绑定。
2. 锁内再次校验旧version、content_hash/canonical hash、chunk/embedding计数和全部新ID冲突；取得完整旧文档/索引/search_text/向量文本及先前绑定，计算规范快照hash。
3. 同一事务持久化完整before快照。只UPDATE目标文档的version/full_text/hash/updated_at，保留source_file、created_at及其他元数据；不得DELETE rag_document或触及会话和其他文档。
4. 只替换目标doc_id的chunk/embedding。新chunk沿用旧source_file并完整填充搜索字段，新版本keyword不生成或冒用旧向量。旧5454向量保留在归档，仅用于精确回滚，不执行embedding模型。
5. 同事务持久化manifest原始文本/hash绑定并核对完整after快照、所有检索字段及目标embedding=0，再commit。源绑定门禁不能代替全行快照与DDL实际验收。
6. commit/传输状态不确定，只读查询精确release_id及after快照；不存在记录仍不得自动断言未发送/重试，须排除未结束事务。重复release_id不能作为自动重放入口。
7. 回滚须匹配该release_id及精确after hash、没有后续漂移；单事务恢复旧文档/完整索引/原vector值和先前绑定，核对before hash并保留release审计。不得DROP新表或覆盖后来版本。
8. 源库发布后才接入完整读取的运行时门禁；从已验收V26/V32冻结字节构建，禁止上传本机旧代理整体覆盖。读缓存身份包含源manifest/版本/hash，且缓存不能掩盖实际索引删改。

禁切换管理器和8093升级仍待其授权/验收；底座固定`chiqiongblastfuenace:latest`与`e4ad74…d8124`，不以其他模型继续测试。30个标准冲突和89个oracle阻断继续单列；822原失败/partial题0次复问，0语义销项，不能报告优化后准确率。
