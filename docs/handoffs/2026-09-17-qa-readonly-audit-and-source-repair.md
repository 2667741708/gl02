# 智能助手只读审计与制度原文解析修复

状态：本机修复、151项回归及独立审查通过；生产知识库未更新。
最后核对：2026-09-17。权威来源：Reliable SSH只读探测、原始DOCX、冻结旧解析器与本轮修复及回归。
适用边界：REQ-QA-READONLY-AUDIT-20260917、BUG-QA-REGULATION-CLAUSE-DROP-20260917，关联QAOPT-K03/K06。本轮不更换模型、不发送原题、不修改数据库或计划任务。

## 已确认的问题与修复

1. 四个只读审计入口先调用raw_pg_connect，再SET TRANSACTION READ ONLY。assistant_pg的普通连接/池配置可能先调用ensure_schema_namespace，在schema不存在时尝试CREATE SCHEMA。历史运行不因此被认定发生了写入，但旧入口不能保证从连接建立起只读。
   - 新增[readonly_pg_connect:L59](../../tools/qa_readonly_pg.py#L59)，在PostgreSQL连接启动参数中启用default_transaction_read_only=on，保持autocommit=False，绕过池/初始化；第一条SELECT校验默认与当前事务只读、实际schema。
   - 默认单语句20秒、锁等待3秒、连接不超过8秒；schema标识符校验，任何退出rollback并close，禁止commit。受控审计接口仅支持一个SELECT及绑定参数，不作为任意SQL沙箱。
   - 四个入口均迁移；PgCompat参数兼容不变。[回归](../../tests/test_qa_readonly_pg.py)覆盖初始化禁调用、状态不符、超时/标识符注入、SQL写入/多语句、异常退出及实际兼容连接。
2. 知识manifest审计原先输出source_file及enriched_content前350字，可能带入用户路径和条款原文。
   - 删除相关查询和输出，文档/样例字段使用白名单，候选completion仅输出complete/terminal_state/reason；实际main回归验证隐私字段和原文不输出。
3. [match_regulation:L149](../../tools/build_three_rules_hierarchical_kb.py#L149)在27/28章无条件回退到章节制度名，parse_source_items把不超过80字的片段均跳过；条款提及规程时也可能被当成标题。
   - 改为整行标题识别、明确编号去除及原书实际标题变体映射；不按句中关键词判断。多行和表格不是标题，正文、表格原文不改写。
   - 原书的工艺技术/设备维护标题及已确认错字、混合编号只用于类别映射，不擅改正式条款。实际DOCX中所有26岗位的三种规程加两章制度共80组已识别；角色和条款语义仍需独立审核。
   - [55项标题与源解析回归](../../tests/test_three_rules_heading_boundaries.py)覆盖两章短条款/表格、句中引用、各种实际标题及保持原文。

## 真实核查与修复前后

只读探测未上传远端文件，通过已审查源码stdin执行；仅从受控配置在进程内读取连接参数，不打印凭据。
数据库default_transaction_read_only和transaction_read_only均为on。
生产r3仍completed：953题/953请求，无活动题，初始PID已不存在；8093保持V26提交7d8a2b1，代理hash保持47b7e75f6a4c2b932ac21b0dd9628d4c049f7a6f2ee083537bbedf1a6c57f431。

| 核对项 | 旧解析/生产 | 本机修复抽取 |
|---|---:|---:|
| 章节 | 28 | 28 |
| 原子片段 | 4540 | 4663 |
| topic | 805 | 803 |
| section | 109 | 121 |
| 27章片段 | 3 | 54 |
| 28章片段 | 11 | 83 |

两章补回51+72=123个片段。计数变化不能代替逐项语义验收，topic/section是结构重分组，不能作为丢失/正确性的单独判断。
原DOCX SHA-256：c5f5578616ebfe7bbbfcc10a7710281c3c4e511361572addc47de56e95a8a541。
冻结旧解析器3ca09d9的DOCX抽取哈希与生产canonical全文哈希相同：96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e。
修复后的抽取哈希：fbf5835be19c6a3dbd8c21489529ed2dd219c3ede634d5729e65d1396f1cb092。

生产full_text是vectorize_three_rules_rag以atomic内容拼接的派生全文；本轮未识别到岗位/规程标题和目录。其与同一索引互证覆盖，不能独立证明原DOCX完整。记录的source_file路径不存在，但本机原DOCX可用；不据此声称原文丢失。

## 验证命令与成功信号

```text
python -m pytest -q --basetemp=.codex_runtime/qa-source-heading-20260917-r4 tests/test_three_rules_heading_boundaries.py tests/test_qa_readonly_pg.py tests/test_qa_document_integrity.py tests/test_qa_document_knowledge.py
```

151 passed：55源标题、52只读审计、44既有文档合同。只读工具与最终标题修复的独立审查均PASS。

```text
python -X utf8 tools/audit_qa_source_docx_readonly.py --docx <受控原始DOCX路径> --expected-authority-hash 96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e
```

对旧authority的预期信号为authority_bytes_match=false、退出1：修复后源抽取确实不同，必须重新审核/发布知识库；不是语义失败或自动批准更新。该程序只输出哈希/类别计数，shared_source_parser_preparation_only、semantic_passed=0。

机器证据：[只读快照及解析修复](../../tests/qa_regression/readonly_audit_source_repair_20260917.json)。本轮0模型调用、0问题POST、0数据库写入；固定底座名称/摘要保持。151本机通过不计入线上准确率或QAOPT销项。

## 后续受控步骤

1. 从已核对DOCX冻结新增/分类变化片段的哈希、原始块位置、岗位及规程分界，独立审核短条款、表格和标题变体；不只对派生全文做自我覆盖验证。
2. 准备精确doc_id知识库候选，保存旧来源/版本/索引与回滚证据；只更新该正式文档，保留会话、其他文档、原始测试结果与oracle历史。不得直接运行现有广泛DELETE导入脚本代替受控发布。
3. 在数据库写入授权及发布审查完成后受控发布，复核源hash、完整结构和实际查询，再逐项审查30个源/标准冲突；89个oracle_blocked不全部归因于本缺陷，也不自动改标准。
4. 生产固定底座管理器安装及8093候选发布仍待完成。仅名称和冻结摘要均通过时，串行复问已证明未发送的822原失败/partial题；未知发送题禁止重放，报告传输完成、答案正确及可回答率的独立指标。
