# 推荐操作值显示为 0 修复交接

日期：2026-08-07  
需求编号：`REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807`

## 问题与根因

页面截图中的“冷风压力建议 0.0”和“喷煤设定建议 0.0”并不是规则生成的调节目标。8768 对 `blocked`、`needs_data` 动作按合同返回 `recommended_target=null`、`recommended_change=null`；旧前端使用 `Number(null)`，JavaScript 将其转换成 `0`，于是把“无可执行目标”伪装成了 0.0。

明确的严重异常停煤到 `0 t/h` 仍是合法数值目标，状态保持 `manual_confirm`，不会被本修复隐藏。

## 修复

- 页面增加 `bfFiniteControlNumberV3`，只把有限数值转换成数字，`null`、`undefined` 和空字符串保持为空。
- 阻断/缺数卡片改为显示“安全门禁已阻断调整”或“数据不足，不生成调整量”，不再显示伪造的 0.0。
- 完整动作详情的当前值/目标值摘要使用同一安全转换。
- 禁止重新启用旧的 `Q_blast` 调整回退；页面仍保持只读建议和工长审批边界。

代码与测试：

- [前端零值保护](/D:/文件/冀南钢铁运行中第二版本/高炉前端数据/frontend_dashboard_v3.server.html:10506)
- [前端回归测试](/D:/文件/冀南钢铁运行中第二版本/tests/test_zero_recommendation_display.py:1)
- [远端页面修复脚本](/D:/文件/冀南钢铁运行中第二版本/tools/remote_deploy_zero_guard_pages_8093_8094_v2.ps1:1)

## 验证

- `node tools/check_frontend_babel_syntax.js`：通过。
- `python -m pytest tests/test_foreman_dual_control_recommendations.py tests/test_zero_recommendation_display.py -q`：`14 passed`。
- 8093/8094 远端 HTTP：均为 200。
- 8093/8094：均包含 `REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807`，旧 `Number(action?.recommended_target)` 均为不存在，安全转换函数均存在。
- `BFV4PreviewProxy8093`、`BFV4PreviewWs8768`：`Running`；8768、8770、11434 未被页面修复重启。

## 部署

采用 HTML-only 受控闭环：上传已验证的 8093 页面 → 8094 共享页面补丁 → 暂停/恢复 8093 守卫 → 精确重启 8094 → HTTP/资源标记验收。

远端备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\zero_guard_pages_20260807\20260807_102103`。

本次不修改数据库、不修改 8768 规则、不增加生产控制写权限。
