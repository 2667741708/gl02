# 复合任务：保留时间子任务并落实来源禁令

状态：V37-r2本机候选冻结，557项相关回归和独立审查通过；生产未应用。
最后核对：2026-09-17。需求：REQ-QA-COMPOUND-SOURCE-SCOPE-20260917。
关联：QAOPT-R01/R02/R08/R10/K04；权威来源：本机代码差异、实际入口反例、隔离真实PostgreSQL/vector、私有原源读取核验及冻结manifest。
适用边界：任务计划、来源约束、历史选择词及3个代理谓词；不代表822原题已通过或生产准确率改善。

## 逐项问题与修复

| 已证明问题 | 修复与可核对入口 | 验收 |
|---|---|---|
| 制度/历史与明确日期、钟点或窗口数据混合时，独立数据子任务被遗漏 | [任务计划](../../高炉前端数据/智能助手/backend/qa_task_plan.py:393)共用引号感知子句分割；保留外层独立时间数据任务 | 日期、钟点、相对窗口反例保留live_data；资料内部时间/书名不增加现场权限 |
| “不要查询现场数据库”误屏蔽明确要求的历史、报表、制度 | [来源约束](../../高炉前端数据/智能助手/backend/qa_task_plan.py:166)区分no_live_lookup和all_tools_disabled；[历史执行计划](../../高炉前端数据/智能助手/backend/qa_history_compound.py:54)保留允许的非现场域 | 实际历史数据库断言检索成功且仅返回本owner、当前消息之前的内容 |
| 纯历史在默认工具模式下绕过全局禁止 | 冻结代理prepare_qa_chat在读取前要求tool_allowed(search_qa_messages, task_plan) | 实际AST分支合成执行：仅禁止现场查询1次历史读取，禁止工具0次 |
| 拆分制度子句丢失外层禁止，正式入口仍内部执行SQL | [制度复合入口](../../高炉前端数据/智能助手/backend/qa_document_compound.py:13)传播外层all_tools_disabled；[正式公共入口](../../高炉前端数据/智能助手/backend/qa_document_knowledge.py:582)在任何SQL前阻止 | 3个追加实际反例修复后0次读库/0次查询函数调用，dependency_blocked/document_lookup_policy_blocked明确未读取 |
| MCP按笼统“无实时”条件直接放弃允许的报表/历史工具 | 冻结代理qa_mcp_should_use_tools及qa_mcp_tool_loop_async读取allow_mcp_tools | 实际代理函数及异步分支测试区分允许报表、禁止现场、禁止全部工具 |
| 历史选择词误含整个提问或禁令，正常历史被判无匹配 | [history_keyword](../../高炉前端数据/智能助手/backend/qa_history_projection.py:16)从唯一历史子句提取字面主题 | 实际SQLite查询两种常用表述均命中；owner隔离、当前消息截止及通配符字面合同保持 |
| 预取重新规划可能恢复被禁止的现场查询 | [prefetch_plan](../../高炉前端数据/智能助手/backend/qa_document_compound.py:48)保留原计划禁令 | 禁令下allow_prefetch不恢复 |

禁止全部工具时同时关闭search_knowledge并清除不允许的allowed_sources；用户提供的数据仍可分析。
仅禁止现场查询不禁止用户明确要求的制度、历史或报表，不将内部SQL视为规避工具禁令的例外。
代码执行与代码示例禁令保持，未更改模型Prompt目标或放宽身份/同源权限。

## 实测结果与审查

- 初始23项：17fail/6pass；制度内部读库追加3项：3fail，均为实际入口/函数调用反例。
- 补齐制度门禁前V37-r1相关554pass，只作历史过程证据；独立审查当时FAIL，不能以该通过数冻结最终候选。
- 最终V37-r2新增34项，聚焦110pass/4.16秒；相关24模块完整557pass/79.81秒，包括真实隔离PostgreSQL/vector的源发布、入口、来源绑定和读取门禁。
- 3项异步测试适配错误源于选错同步wrapper，改为实际异步入口后执行原断言通过；单列为测试错误，不算产品失败或通过。
- 原始私有源的5587索引、11组制度/章节及14次单快照读取完整保真，1pass/15.77秒；未上传任何原文，不据此推断topic或语义准确率。
- 独立gpt-5.6-luna low修正后复审PASS，确认外层禁令、读库门禁、非现场权限与固定底座均保持。
- 22个共享功能标记通过；3个代理谓词反向恢复后完整AST与V36一致。

完整数量、文件SHA及边界：[脱敏机器证据](../../tests/qa_regression/compound_source_scope_20260917.json)。
可复现相关测试见上述证据与[test_reference](../test_reference.md)；测试临时目录必须位于独立工作树，避免共享Temp权限干扰。

## 冻结与生产边界

[候选生成器](../../tools/build_qa_compound_scope_candidate.py:55)先校验V36的10文件及manifest，再生成15文件候选；8文件逐字节继承，制度读取器及5个来源规划模块更新，代理仅3谓词修改。
私有V37-r1保留，V37-r2无覆盖生成；manifest SHA256 dc5615e765d63c084edd35b7e75532101d41e9e8dc5e61a75e249cce397362ec。
代理SHA256 e9989821d8f64da832a72b5aa67fb54537814a7d569444e2873e4919f122d37e。
制度读取器SHA256 9d8f08049ca2ef17741e72359f7af059b0bded4286a3f0efc5f62655a78e2e23。

唯一固定底座持续为chiqiongblastfuenace:latest，摘要e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124。
名称、同名权重替换、备用回退、接受其他当前驻留或调用参数覆盖全部禁止；不一致阻止调用。
本轮0助手模型调用、0生产写入、0原题发送，33项台账state均保留，0销项。
V27—V37仍未部署；最近成功生产V26核验属于历史快照，当前SSH身份/路线未通过不能宣称生产锁定或就绪。

恢复连接后先只读核验r3进度/进程/版本、固定模型、实例/源/read_set，再按受控8093流程部署。
管理器/恢复任务和DB迁移/源发布分别仍需授权；不扩展到11434、8094、8768等独立服务。
串行复问822原fail/partial题，每题一次；未知发送TPL-10C8C8FAF2C694EF不得重放。首次模型摘要匹配未证明前，禁止声称严格同底座配对或纯代码收益。
