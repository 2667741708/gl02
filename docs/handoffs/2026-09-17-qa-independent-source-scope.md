# 智能助手制度独立源范围校验与冻结候选

状态：本机r2候选冻结、202项回归和独立审查通过；生产知识库未发布。
最后核对：2026-09-17。需求：REQ-QA-SOURCE-SCOPE-20260917，关联QAOPT-K03/K06。
权威来源：经哈希核对的原始DOCX、独立OOXML源位置校验、冻结候选及实际测试。
适用边界：源完整性和血缘；不能作为答案语义通过或线上准确率证据。

## 本轮修复

1. 岗位标题使用明确的整行名称与编号，拒绝正文中的岗位提及、目录和表格作为章节标题；不再使用包含/前缀的模糊判断。
2. 第18章带引号的“三规一制”后缀只作为标题标记处理。第19章原书目录“喷吹工”和正文“喷煤喷吹工”的差异使用仅限19章的显式映射，不扩大到其他岗位。
3. 单列表格即使内容看起来像规程标题也保留为正文；空表格单元格保留分隔位置。规程类别映射不修改原书条款。
4. 新增[独立校验器](../../tools/qa_source_scope_contract.py)：自己遍历OOXML，不调用索引builder的目录、抽取或标题匹配函数。按原始块/行位置、顺序、岗位、规程和内容hash核对。
5. 新增[冻结器](../../tools/freeze_qa_source_scope_candidate.py)：仅在全新、Git忽略的私有目录写入候选。读取一次原书字节，哈希与DOCX解析使用同一BytesIO；所有身份与范围检查通过后才写入。

独立校验仍共享已审查的字面标题映射作为政策数据，不能把它当作第二份工艺标准或语义oracle。

## 实际源校验与候选

| 核对项 | 结果 |
|---|---:|
| 原始章节 | 28 |
| 岗位/规程范围组 | 80 |
| 源内容及atomic | 4663 |
| topic | 803 |
| section | 121 |
| 源item缺失/额外 | 0 / 0 |
| chunk绑定错误 | 0 |

atomic必须逐项完整且有序，section必须按连续原条款覆盖完整范围组，表格不能截断。topic仅核有序源行子集与岗位/规程边界，明确`topic_completeness_verified=false`；不能以此证明topic完整。

原书SHA256：`c5f5578616ebfe7bbbfcc10a7710281c3c4e511361572addc47de56e95a8a541`。
旧生产派生全文：`96fdc3f9ec0a39c226667247ef16295bfa9707e56438c162a7958db96a127b6e`。
新候选全文：`fbf5835be19c6a3dbd8c21489529ed2dd219c3ede634d5729e65d1396f1cb092`。
源manifest：`e3a0a9b1baffd386800bcbd2795338f16dadd40a859dabd4ad4a5ad5c29dc331`。
私有文档候选：`95fa4525c35054f20adacf758d52ef7c3de0cecd98a270e30a66d7ce006d8f7c`。

r1保留历史不可覆盖；r2修复读取/哈希边界，源manifest和文档候选字节保持相同，生成器hash另行冻结。原始正文及候选仅保存在Git忽略的`.codex_runtime/qa-source-scope-20260917/candidate-r2`；只发布[脱敏机器证据](../../tests/qa_regression/source_scope_candidate_20260917.json)。

## 验证与局限

```text
python -m pytest -q --basetemp=.codex_runtime/qa-source-scope-20260917-r4 tests/test_qa_source_candidate_freeze.py tests/test_qa_source_scope_contract.py tests/test_three_rules_heading_boundaries.py tests/test_qa_readonly_pg.py tests/test_qa_document_integrity.py tests/test_qa_document_knowledge.py
```

实际202 passed（1.34秒）；独立gpt-5.6-luna low只读审查PASS。新冻结边界回归起初3项被合成目录未满足实际19章映射阻断；修正测试目录后全部通过，没有放宽生产政策。

本轮固定`chiqiongblastfuenace:latest`及已冻结`e4ad74…d8124`底座，keyword候选不生成embedding。0模型调用、0数据库写入、0问题POST，0语义销项。生产仍V26，r3已953/953完成，无活动题；822原失败/partial复测仍0发送。

## 受控发布和后续验收

1. 准备仅针对正式doc_id的keyword发布与回滚，核对旧authority CAS、旧索引及版本备份；不得运行广泛DELETE导入或embedding脚本。
2. 数据库写入须单独授权；发布成功后核对实际源manifest、全文及全部chunk血缘，运行真实查询。当前候选不是生产发布授权。
3. 把独立源manifest接入完整章节/表格读取的证据门禁；从已接受生产字节构建运行时，不整体上传本机旧代理。
4. 逐项审核30个源/标准冲突，保持旧oracle和原测试判定，不以恢复123片段自动宣布89个oracle阻断已解决。
5. 安装禁切换管理器及8093候选后，固定名称/权重/实际驻留均通过才串行复问已证明未发送的822题。未知发送题不重放。分别报告传输完成率、正确率、部分回答和不可评分题。
