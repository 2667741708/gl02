# 8093/8094 炉况评分与单炉况智能分析交接

追踪编号：`REQ-8093-8094-DIAGNOSIS-REVIEW-AI-20260806`

## 结果

2026-08-06已在220.12的8093和8094启用同一套异常弹窗、八卡手动评分、免登录提交、单炉况v3智能分析、规则变量解释、调剂引擎1建议依据和知识库依据。

截图中的“暂不可用”不是Ollama宕机。8093的直接原因是共享代理已经调用v3单炉况接口，但模型合同和分析API模块仍为旧版；8094则没有启用相关启动变量。两处均已修复。

## 当前合同

- 一次模型调用只分析用户所选的一个炉况；schema为 `diagnosis_ai_analysis.v3`，Prompt为 `diagnosis-single-condition-five-minute.v3`。
- 浏览器只传炉况键。系统分、诊断时间、公式变量、5分钟变化、60分钟统计、30天基线、建议和知识证据由服务端读取。
- 人工评分与建议可选；关闭不提交。提交时系统分与人工分并列追加保存，互不覆盖，并保留诊断时间和提交时间。
- 异常主诊断可自动弹窗；没有自动弹窗时仍可点击任一炉况卡手动打开。
- 8093、8094均为免登录现场提交；历史查询和其他受保护接口不因此开放。

## 部署与隔离

- 8093回滚目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\diagnosis_ai_analysis_20260806_072403`。
- 8094回滚目录：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs\deploy_backups\8094_diagnosis_ai_20260806_073217`。
- 8094部署仅将自身PID从 `14416` 更换为 `17348`；8093、8768、8770和11434 PID不变。
- 8094继续使用共享 `ollama_proxy_server.py` 和8768；不得运行历史的8769/隔离代理部署方案。

## 验证

- Python回归：`46 passed`；新增8094部署合同所在测试文件单独复跑 `12 passed`。
- 8093部署：HTTP 200、评分上下文可写、免登录、真实分析完成，变量/建议/知识依据存在。
- 8094部署：`pageInjected=true`、`contextCanSubmit=true`、`loginRequired=false`、`analysisState=completed`、`analysisSchema=diagnosis_ai_analysis.v3`，变量/建议/知识依据均存在。
- Chrome实际点击：8093和8094的“正常顺行”卡均能打开组合弹窗，状态最终为“已完成”，四个核心分析区块完整出现。跨入新5分钟桶时会先短暂显示“分析中”，完成后前端自动轮询更新。
- 空模型复核和空手动评分请求均返回400，仅验证路由与校验，没有写入伪造验收数据。

## 排障入口

先比较共享代理与 `diagnosis_model_review.py`、`diag_ai_evidence.py`、`diagnosis_ai_analysis_api.py` 的版本/哈希，再检查进程环境开关。不要仅凭 `/api/ollama/status` 正常就认定整条智能分析链路正常。详见[排障手册](../troubleshooting.md#80938094-炉况卡显示智能分析暂不可用)。
