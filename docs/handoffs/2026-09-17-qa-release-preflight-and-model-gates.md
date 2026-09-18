# QA 发布预检绑定与停服前固定底座门禁

状态：本机实现、实际隔离回归和独立只读审查通过；未生产执行，不授予模型或任务修改权限。
最后核对：2026-09-17。
需求：REQ-QA-RELEASE-PREFLIGHT-BINDING-20260917、REQ-QA-PRESTOP-FIXED-MODEL-GATE-20260917。
权威来源：实际Git夹具、实际PowerShell函数执行、root回归输出及现有gpt-5.6-luna独立审查。
适用边界：发布预检证据与固定模型元数据门禁，不是生产身份锁定或原题回答准确率。

## 修改与原因

- [validate_preflight_evidence](../../tools/record_qa_release_preflight.py#L12)替换旧全仓HEAD相等限制。允许基准后的无关提交，但两份只读证据必须观察同一HEAD、相同基准和仓库/分支、完整读写路径与候选/staged摘要。拒绝冲突、范围内脏改动、EOL迁移、truthy标志和空/重复/缺失证据。返回deployment_authorized=false、model_identity_verified=false，不能把可记录当成获准部署或模型健康。
- [Assert-FixedModelIdentity](../../tools/remote_guarded_deploy_qa_routing_v3_8093.ps1#L222)只执行GET tags→ps→tags，严格核验名称chiqiongblastfuenace:latest与完整批准e4ad…8124摘要，ps要求唯一匹配驻留。
- 实际调用位于外层停服/取锁前[L287](../../tools/remote_guarded_deploy_qa_routing_v3_8093.ps1#L287)、锁内备份/停服前[L301](../../tools/remote_guarded_deploy_qa_routing_v3_8093.ps1#L301)、恢复后的readiness验收[L331](../../tools/remote_guarded_deploy_qa_routing_v3_8093.ps1#L331)。未驻留或错误摘要在停服前失败，不warm/cp/switch/unload；切换后验收失败继续既有finally/rollback。

该检查只阻断不符合身份的发布；旧恢复器仍可能继续改写模型，生产永久固定另见[独立根因](2026-09-17-model-identity-switch-independent-audit.md)与[固定策略](2026-09-17-qa-single-base-model-policy.md)。

## 实际验证

1. 真实Git路径范围与预检绑定：**69 passed，106.58秒**。读取生产模拟index/HEAD/status前后保持不变，覆盖无关提交与暂存项、候选字节、scope完整性、schema/旗标、观察HEAD不一致及错误证据。
2. 实际PowerShell身份门禁与既有readiness：**21 passed，15.28秒**。覆盖错误/缺失/重复标签、空/错误/多驻留、末次标签漂移、GET异常和调用顺序；不执行真实服务或模型操作。
3. 现有独立reviewer gpt-5.6-luna只读审查PASS；没有访问生产、没有修改文件、没有实际部署。

```powershell
python -B -X utf8 -m pytest tests/test_qa_release_preflight_binding.py tests/test_qa_deployment_path_scope.py -q --basetemp .codex_runtime/qa-release-binding-tests-r1
python -B -X utf8 -m pytest tests/test_qa_fixed_model_deployment_gate.py tests/test_qa_release_readiness.py -q --basetemp .codex_runtime/qa-fixed-deploy-gate-tests-r1
```

上述basetemp已使用，复现必须选择未存在的新目录。测试不属于822原题真实复测，不能加入原题成功率或准确率分母。版本注册、密封发布及新底座管理器安装仍按各自闭环执行，未在本文执行。
