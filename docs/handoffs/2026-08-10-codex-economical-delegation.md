# Codex经济型委派与8093快路径交接（2026-08-10）

追踪编号：`OPS-CODEX-ECONOMICAL-DELEGATION-20260810`。

## 结论

本机Codex CLI为`0.144.3`，当前账号实时可见`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-5.6-luna`等模型。已创建全局`codex-economical-delegation` Skill；低风险语义任务默认Luna low，确定性任务不调用模型。

8093小改动采用“quick本地验证、复用SSH、在线预暂存、一次停改启、定向生产冒烟”的快路径。Skill能保证默认流程和计时口径，不能保证每次绝对耗时；网络、测试失败、服务启动、基线冲突和回滚仍会改变结果。

## 安全边界

Luna/Terra worker只允许本地只读定位、清单、脱敏失败分类、测试建议和精确所有权的本地修改。220.12凭据、远程命令、上传、部署互斥、8093服务停启、原子替换、回滚和最终生产验收由主任务独占。

## 实测

- 未最小化Luna low：89004ms；input 58097、cached 27392、output 184。
- 最小工具/4KB项目指令：29197ms；input 38309、cached 17152、output 235。
- 两次都正确读取`validation_matrix`并返回default quick、4/17/85。
- 优化后耗时下降67.2%、输入下降34.1%；仍有WebSocket失败后回退HTTP的网络延迟，因此固定命令不应委派给模型。

## 入口

- Skill：`C:\Users\hmw20\.codex\skills\codex-economical-delegation\SKILL.md`
- 包装器：`C:\Users\hmw20\.codex\skills\codex-economical-delegation\scripts\invoke_codex_delegate.ps1`
- 模型路由：`C:\Users\hmw20\.codex\skills\codex-economical-delegation\references\model-routing.md`

本次没有连接或修改220.12/8093生产。
