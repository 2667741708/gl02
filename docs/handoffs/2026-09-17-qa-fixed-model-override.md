# 唯一固定底座：禁止调用参数覆盖身份

状态：V36-r1本机候选冻结，61项相关回归及独立语义审查通过；生产未应用。
最后核对：2026-09-17。需求：REQ-QA-FIXED-MODEL-OVERRIDE-20260917。
关联：QAOPT-O01/T03/T05；权威来源：本机真实代码差异、身份反例、隔离PowerShell函数harness及冻结manifest。
适用边界：固定底座身份入口；不是所有路由/生产管理器或822原题语义验收。

## 已证明问题及修复

旧resolve允许显式传入name/digest。即便默认值是冻结底座，只要合成tags和ps与调用值一致，另一批准版本、另一模型名称甚至缺失名称/摘要都会被接受。
这不是本轮发现生产已切换的证据，但违反“始终完全相同底座”的入口合同。

现在[resolve](../../高炉前端数据/智能助手/backend/qa_fixed_model_identity.py:30)在任何回调/上游GET前检查参数必须等于硬编码名称/digest；不一致抛FixedModelUnavailable，稳定code保持fixed_model_identity_not_ready。
显式传入相同pin继续兼容，后续tags→ps→tags、唯一驻留、总时间预算和取消传播保持；不热身、不更换alias、不切模型或重发问题。
模块版本qa-fixed-model-identity-v2，模型名称和权重摘要均未变。

## 实测与边界

- [身份回归](../../tests/test_qa_fixed_model_identity.py)新增6例：5种非法覆盖及1个显式同pin对照。旧模块实际17项5fail/12pass；修复后17pass（0.05秒），非法覆盖断言0GET。
- 身份、代理真实替换函数、单底座管理函数、安装事务及旧窗口退役五组最终61pass（38.05秒）；PowerShell真实执行于合成harness，不触及生产任务或模型。
- 先前一次38pass/23setup errors为Windows默认pytest临时目录权限拒绝；改用独立工作树basetemp后完整执行通过，未修改共享ACL或删除其他目录。错误不算产品失败也不算通过。
- 独立gpt-5.6-luna low只读语义审查PASS，确认没有改变取消、预算、同权重版本驻留或生产授权边界。
- V35源/制度400项为前阶段实际结果，V36没有重新执行这一组；源读取器/门禁及其余9文件逐字节保留。不能虚构当前461项合并运行或据此推导原题准确率。

命令、摘要、数量与边界：[脱敏机器证据](../../tests/qa_regression/fixed_model_override_20260917.json)。

## 冻结与当前权威

V36-r1私有候选10个Python文件及manifest；manifest SHA256 d624e06065f0f9752b7d4b44464171f391e4ace6ca94c18f718db9c018510aee。
身份模块SHA256 58ed219087a64140b989cc5d4c48c72f1f4b039660530bf71871b938c4de8217。
其余9文件与V35完整相同，候选模块导入及非法覆盖0GET拒绝独立验证。冻结尚非生产密封，仍需在线read_set/recordability重核。

[完整优化方案](2026-09-17-qa-full-optimization-plan.md)改为唯一固定底座执行顺序；K04保持V34重新开放的partial状态。
[旧V26窗口](2026-09-17-qa-v26-model-window.md)显式标为历史退役，不再按两个批准版本、动态冻结当前驻留或切换冷却执行。
台账current_local_candidate记录实际V36，旧V26记录原样保留；33个问题state不变，本轮0销项。

## 生产条件与剩余工作

固定chiqiongblastfuenace:latest及e4ad74c41d68de1c8004419d8141a2b2df2275fa08f0dcf326ca0e63fb6d8124。任何同名换权重、备用回退或当前另一个驻留摘要都不能成为新基线；不一致时停止下一模型调用。
本轮Reliable SSH身份和显式路线探测失败，无生产命令派发；最近成功核验生产V26仅为历史快照。V27—V36未部署，0模型调用/生产写入/原题发送。
管理器/恢复任务安装及DB迁移/发布/回滚仍分别待授权与验收，8093代码授权不扩大到其他服务；不能靠切模型恢复测试。

连接恢复后只读重核r3进度/存活/版本哈希、固定模型与源基线/实例/config/read_set，复用受控8093闭环和独立源发布包，再串行复问822原失败/partial题，每题一次。
未知发送TPL-10C8C8FAF2C694EF永久禁止重放；提交或传输不确定先只读恢复。
首次结果的模型摘要未证明完全匹配前不得宣称严格同底座配对或纯代码收益；保留原ID/判定/哈希，分别报告传输、语义、部分及标准/证据阻断。
30原源标准冲突、89oracle阻断及topic/语义审核继续单列，不能销项为通过。
