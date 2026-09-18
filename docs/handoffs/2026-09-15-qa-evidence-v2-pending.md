# 智能助手两阶段修复交接

- 需求：REQ-QA-NO-CODE-EVIDENCE-BASELINE-20260915。
- 最后核对：2026-09-15。
- 状态：V1 已上线并复测；V2 已密封，远程连接失败，未切换。
- 权威源：本工作树 .codex_runtime/qa-release 的密封清单、记录性检查与候选字节；回归工作树 tests/qa_regression 的脱敏报告。

## 已完成
V1 远端提交 9d2393d9c1e0f5558af3b52f2eaaa02737cff8f8，8093 PID 11864 → 12572，受保护端口进程保持不变，守卫恢复，无回滚。
V1 8 题复测：4 题满足主要合同，4 题未通过或部分完成。保留数学和已有数据分析，已测代码示例关闭。

V2 基于经过核实的 V1 生产字节，仅改代理与 qa_evidence_policy.py。19 项针对性测试通过、421 个未修改定义保留、共享功能门禁及独立 Luna 审查通过；临时索引证明可记录、无换行迁移。

## V2 密封证据
- production base: 9d2393d9c1e0f5558af3b52f2eaaa02737cff8f8
- proxy SHA256: c94dc585cd0d319ae9ef2235620acd7802d880f569510dac43c2e571a0e6298c
- policy SHA256: 442ea9df0f2ab41738b8b9613491dcc4838890800974f96c3d8ccf27a2369d4d
- prepared manifest content SHA256: 29A3B99BD2F8B0E4DDD41A2073A59494C5E3615C363011EF3E952502AD58BE30
- delta-plan file SHA256: 629055CECAFA9697594282ACAF659CB822C948AA97891F0D037890B1551EF163
- scope-gate file SHA256: A65A81B8BD3D8B5084731F10AB5C98CD4172CB30366464D27C7FF30D4F207982
- stage: C:/Users/Administrator/AppData/Local/Temp/qa-evidence-20260915-v2
- target root: F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW

六个候选与检查文件的 upload-only 已确认成功。后续 delta-plan.json 上传超时，上传状态不确定；只读文件检查和身份探测均超时。未调用部署器，不允许推断 V2 已生效。

## 恢复后步骤
1. 用 Reliable SSH 核实身份、生产版本、两个目标与三个依赖哈希、端口 PID、暂存 delta 文件；不可自动重放。
2. 若生产仍为 V1 且候选密封有效，重新生成新鲜 remote-state 和 delta；确认上传后执行受控 deploy.ps1，只切换 8093。
3. 验收部署结果与模型状态，再用现有收集器 phase=after-v2 逐题一次 POST；不得覆盖 before/after 文件。
4. 尤其检查 LIVE-001/003/007/008。若综合仍异常，查看 qa.analysis.failed 的类型及状态，不能先提高工具预算。
5. 完成运行时验收后，用 V2 record script 和对应 operation/record-plan 记录实际安装的两文件。不能使用 V1 stage 或旧 Git head。
6. 更新 GitHub PR #1；公开只保留合成题和脱敏汇总。

## 本地验证
python -X utf8 -m unittest discover -s tests -p test_qa_evidence_policy.py -v

精确生产代理候选保存在忽略目录，不能用此工作树中旧的已跟踪代理文件替换。构建器及 changes.json 记录了相对于 V1 的最小变更。原始现场结果仅在受控忽略目录，不上传 GitHub。
