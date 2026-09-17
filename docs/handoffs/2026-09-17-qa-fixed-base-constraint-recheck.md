# 固定底座强约束复核

状态：本机约束回归通过，生产管理器尚未更新；最后核对：2026-09-17。
权威来源：本轮Reliable SSH只读GET、固定底座模块及实际PowerShell隔离测试。
适用边界：REQ-QA-SINGLE-BASE-MODEL-20260917；不授予计划任务或模型管理器写入权限。

## 强约束

- 唯一模型名称为chiqiongblastfuenace:latest，唯一权重摘要为e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124。
- 禁止自动切换、备用底座、同名权重替换及把漂移权重接受为新基线。
- 固定底座身份不一致或不可用时，候选返回fixed_model_identity_not_ready；不切换模型或自动重发原题。
- 同一已批准权重的冷启动不构成更换底座，但必须按已授权管理流程执行。

## 本轮核对

生产GET快照显示：固定名称没有匹配冻结摘要，驻留列表为空；旧管理器SHA-256仍为856f38b6edb088327e2138b88e68961db1a153b451aedb6709bea9fd2a8e99fa。这只代表本次快照，不能据此判断其他权重当前正在运行。r3保持completed，953题、953次请求，无活动题。

已停用的历史双底座窗口仍有旧测试期待它运行，导致5项断言失败。更新[test_qa_fixed_model_window.py](../../tests/test_qa_fixed_model_window.py)的六种隔离场景：必须拒绝执行；任务状态不变；无任务读取/修改、HTTP调用或输出目录；不恢复历史双底座逻辑。生产代码和候选发布字节没有改变。

验证：python -m pytest -q --basetemp=.codex_runtime/qa-fixed-base-check-20260917-constraint-r2 tests/test_qa_fixed_model_identity.py tests/test_qa_single_model_guard.py tests/test_qa_fixed_model_window.py tests/test_qa_fixed_manager_install_transaction.py

结果：47 passed。首次运行另遇默认临时目录权限错误，改用独立工作树临时目录后运行；没有修改目录权限或清理其他测试资产。

本轮零生产写入、零模型POST、零原题发送。47项本机通过不能作为线上准确率。生产管理器安装及8093候选更新仍未完成；保持原有单独授权边界。
