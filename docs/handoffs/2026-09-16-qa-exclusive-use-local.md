# 智能助手全角色独占使用

- 状态：V21已受控发布；本机验证完成，真实双角色409/取消现场验收待测。
- 最后核对：2026-09-16。
- 需求：`REQ-QA-EXCLUSIVE-USE-20260916`；关联QAOPT-O05。
- 权威来源：用户“多角色并发限制同一时间只能有一个人使用”、当前生产控制模块只读基线、本机代码与生命周期测试。
- 范围：8093问答请求生成期间；不限制页面浏览/只读历史，不占用整个登录会话，不扩展8094或Ollama服务配置。

## 行为

访客、操作员、管理员及不同私有会话共用一个活动问答名额。第一请求在新请求注册阶段占用，覆盖准备、工具调用、生成及清理；其他人发送返回HTTP409：`error=assistant_in_use`、明确“正在使用中”消息、`automatic_replay=false`。不返回占用者owner/会话/请求ID。

取消信号发出后仍占用，直到实际问答停止、finally设置finished才释放；失败同样释放。释放后需要新的人工发送，不自动重放被拒绝的请求。原有身份、owner、同源和取消边界保留。

## 实现

基于实际生产 `qa_request_control.py`，仅在现有注册锁 `_lock` 内新增一个全局活动请求检查；无需新增等待队列或持有数据库连接等待模型。检查在新RequestState和原始问答执行前，因此被拒绝请求不进入问答工具或模型，不注册生成请求。

模块和符号：[qa_request_control.install](../../高炉前端数据/智能助手/backend/qa_request_control.py#L65)、[wrap.run独占检查](../../高炉前端数据/智能助手/backend/qa_request_control.py#L135)。生产只读基线在忽略目录保留，任何发布必须重新核实当前HEAD及模块哈希。

## 本机验证

`python -X utf8 -m pytest tests/test_qa_exclusive_use.py tests/test_qa_context_provenance.py tests/test_qa_retest_persistence.py -q --basetemp .codex_runtime/pytest-exclusive-new-run`

- 35项通过，其中独占9项：6组角色对、取消中继续占用、失败释放、同时注册竞态。
- 独立应用审查PASS，复验9项通过；未发现跨角色绕过、取消提前释放、锁等待模型或私有ID泄露问题。
- 真实控制模块离线执行，全部身份和响应均为合成夹具；0生产问答POST、0模型调用、0远端写入。
- 仿真角色覆盖不等于真实受控operator/admin登录生产复测。
- 当前实现为单8093进程内的全局注册门。当前受控服务为单进程；如果未来扩展多进程/多实例，需共享独占协调，不能用本机锁声称跨实例互斥。

## 发布验收要求

V21已按8093受控流程发布精确模块，其他服务PID保持不变；[生产与复测证据](2026-09-16-qa-routing-v21-paired-retest.md)。新轮真实双请求必须有各自一次claim：一个进入、另一个409且无工具/模型调用；前请求完成后新人工请求可进入。取消与异常释放也需验证。模型驻留/Qwen配置保持独立事项。
