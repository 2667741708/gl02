# 8093处置首屏与工艺依据按钮上线记录

需求编号：`REQ-8093-ABC33-ACTION-FIRST-BASIS-TOGGLE-20260810`

## 页面结果

- 进入任一ABC33复核详情后，状态区下方首先显示完整“处置顺序”。
- 新增“查看工艺依据与操作原理”按钮；默认收起，点击后显示“工艺依据”和“操作原理”两块内容，再次点击收起。
- 8093生产操作详情不再渲染“见习高炉长手册·第X章”等来源索引。
- 来源索引仍保留在后台规则目录和审计数据中，没有删除来源血缘。
- 8094通过端口分支保持原详情布局。

## 修改与验证

- 页面资源：[abc-furnace-rules-production.js](../../高炉前端数据/assets/abc-furnace-rules-production.js)
- 缓存版本：`abc33-20260810-action-first-basis-toggle-r1`
- 专项测试：`pytest tests/test_abc_production_ui.py -q`，`7 passed`
- JavaScript：`node --check`通过
- 生产详情：B4返回5步`intervention_order`和有效`principle`
- 生产入口：`http://10.30.220.12:8093/?cb=abc33-20260810-action-first-basis-toggle-r1#optimization`

## 受控部署证据

- 备份：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\backups\abc33_action_first_basis_toggle_20260810_150003`
- `BFV4PreviewProxy8093`：守卫已暂停并恢复，PID `7400 -> 13064`
- 8093：HTTP 200
- 8094 PID：`2988 -> 2988`
- 8768 PID：`18436 -> 18436`
- 8770 PID：`3732 -> 3732`
- 11434 PID：`5968 -> 5968`
- 8094页面文件：部署前后SHA-256一致
- 生产资源SHA-256：`E93E50C20516F415E4478AFDB9A9FCBDC27108C059D7313A5684F095E5D6D359`
- 8093页面SHA-256：`491D46C4F956D19C9E592FF3C6694AA58A57F5A60FFEF20DFB4CCF211E8B1B2F`

## 浏览器说明

带新缓存版本的8093页面能够完成导航并返回正式页面标题。生产页面持续执行大量实时渲染时，自动DOM深层读取出现超时，因此本次交付没有把该超时错误描述为“控制台零错误”；页面合同、生产资源、API和守卫闭环均已独立验证。

## 回滚

如需回滚，只恢复上述备份中的`abc-furnace-rules-production.js`与`frontend_dashboard_v3.server.html`，再走同一8093守卫停—改—启闭环；不得停止8768、8094、8770或11434。
