# 8093 ABC33 建议不可用权限修复交接

- 状态：生产已修复
- 最后核对：2026-08-12 08:13（Asia/Shanghai）
- 错误编号：`ERR-8093-ABC33-EXPLANATION-PERMISSION-20260812`
- 适用范围：220.12 的 8093 参数优化页、ABC33 解释弹窗与 8768 工长建议合同

## 结论

33 项 ABC 规则计算没有失效。稳定故障是公共页面调用确定性解释 GET 时被错误要求
`operator/admin` 权限；前端又将其与受保护的会话创建一起判为整窗失败。截图中 8768 合同提示
是同时发生的瞬态：部署前后的真实 `init`、`tick` 均返回 8 个条件和 16 个动作，未修改其
fail-closed 合同。

## 修复边界

1. `GET /api/furnace-rules/{rule_id}/explanation-context` 作为公共 latest/detail 的只读展开，允许
   匿名读取；不写库、不创建会话、不调用模型。
2. `POST /api/qa/contextual-conversations` 与 `/api/qa/chat` 继续要求受控登录、owner 隔离、同源
   校验和固定首问。
3. 前端分别处理两种能力：确定性上下文可用时先展示；会话无权限只提示“登录操作或管理账号后
   可继续对话”，不再覆盖为“规则分析接口暂不可用”。
4. HTML/JS 资源版本升级为 `abc33-context-assistant-20260812-r2`，避免浏览器继续使用旧缓存。

## 部署与回滚记录

- 执行 ID：`abc33-advice-20260812-0810-0f2def98`
- delta manifest SHA-256：`ACA840D0E9DA9B0BC606F4AB7F2C5DA494A7C86C30250E4FB077A7BAF4B0B523`
- 包 SHA-256：`0F2DEF98D0F2AC87E8138C753116786881C917BF18D8EC11BF2C3218E6DC8D03`
- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_contextual_assistant_8093_20260812_081106`
- 守卫：`guard_paused=true`、`guard_restored=true`
- 回滚：正式成功轮 `rollback_applied=false`；首次 SSE 验收传输关闭轮已自动恢复应用文件，数据库
  仅保留幂等加法迁移。

安装哈希：

- `frontend_dashboard_v3.server.html`：`62FE1AEB042CC88EEE4976D5188DD6919DB6C0D48A27F8CAB7AA16683928EDB5`
- `bf-abc33-assistant-dialog.js`：`E4F20E46C3FFEB29DB73009D4CE2B1A86052D7EAF6128191B9B8B8DA70D0E4CF`
- `ollama_proxy_server.py`：`692316F2D9817B46980A66F8A75E78429BE6F8BF2787068B2265F220046C7CBA`

## 验收证据

- 聚焦测试：46 passed。
- 匿名真实链路：latest 返回 evaluation，explanation-context 从部署前 HTTP 403 变为部署后 HTTP 200。
- 会话合同：受控账号可创建/复用 ABC contextual conversation；本次 quick 修复未重复触发模型 SSE。
- 进程隔离：8093 `9692→16452`；8094=`5912`、8768=`9084`、8770=`3732`、
  PostgreSQL=`12372`、Ollama=`16232` 保持不变。
- 页面矩阵：Chromium `1366×768`、Chromium `390×844`、Firefox `1366×768`、WebKit
  `1366×768` 共 4/4；33 个入口存在，弹窗为 `context_ready`，无横向溢出或阻断错误，模型真实
  请求数为 0。报告位于 `logs/abc33_advice_fix_quick/`。
- 8768：`init` 与 `tick` 均通过 `verify_foreman_dual_control_runtime.py`，8 条件、16 动作，当前
  状态计数为 eligible 10、blocked 3、manual_confirm 2、needs_data 1。

## 防复发

任何后续修改必须同时测试“真实匿名 explanation GET”和“受控 contextual POST”，不能只使用带
鉴权浏览器夹具。前端测试必须覆盖“GET 成功 + POST 403”仍显示确定性上下文。8768 建议异常独立
按完整合同核查，不以降低字段要求或静默接受残缺帧作为修复。
