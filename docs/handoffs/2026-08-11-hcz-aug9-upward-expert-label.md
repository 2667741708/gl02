# 2026-08-11 HCZ 8月9日上移专家弱标签交接

追踪编号：`Q-HCZ-AUG9-PSPACE-LABEL-UP-20260811`  
执行时间：2026-08-11 11:30（Asia/Shanghai）

## 结果

已按用户现场确认，把2026-08-09的事件追加为软熔带“上移”专家弱标签：

- `id=1`
- `reference_id=HCZ-28cf0aad-63af-4e64-a27d-679ca79dbfdd`
- `observed_at=2026-08-09 22:00:00+08:00`
- 证据窗口：`2026-08-09 20:00`至`2026-08-10 06:00`
- `movement_label=up`
- `root_level_label=uncertain`
- `confidence_grade=4`
- `reference_type=expert_weak_label`

该记录只确认移动方向。没有直接HCZ几何测量，所以中心高度、厚度和绝对高低不填写；不得把它称为直接真值或用于自动控制。

## pSpace四点顶温证据

通过220.12直连pSpace `10.22.181.243:8889`，以`PS_HIS_AVERAGE`读取一分钟处理历史：

| 时刻 | T_top_A | T_top_B | T_top_C | T_top_D | 四点均温 |
|---|---:|---:|---:|---:|---:|
| 08-09 20:00 | 108.607 | 110.008 | 107.843 | 110.860 | 109.330℃ |
| 08-09 22:00 | 126.278 | 122.912 | 125.063 | 124.660 | 124.728℃ |
| 08-09 23:00 | 127.595 | 125.776 | 123.590 | 125.598 | 125.640℃ |

20:00至22:00四点均温约上升`15.399℃`，四个测点同向变化。pSpace审计窗口为20:00至次日07:00，返回`errors={}`，证据SHA-256为`14a3d5fc9bc90897a59ab2e8f570eec3e69cf8e1a5f7c752e37041632f8e2e85`。

四个标签分别为：

- A：`\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0040`
- B：`\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0064`
- C：`\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0072`
- D：`\冀南钢铁\SIO\GL02\LD\SIO_GL02_LD_T0043`

## 标签写入证据

写入前8月9日至10日标签数为0。8892在POST前重新读取实测窗口并生成：

- `source_data_hash=1cd05b954ab2053a1ccad58c27ae78e7a5dfd274b1a363cc345cafcda256163e`
- `measurement_record_count=52478`
- `primary_coverage=0.928571`
- `context_mode=retrospective_with_post_observation_evidence`
- `blind_to_model=true`
- `model_outputs_included=false`

POST返回`created=true`，随后GET按观察时刻、移动方向和数据哈希回读，精确命中1条。操作只向`bf_assistant.hcz_expert_label_events`追加该记录；没有修改传感器数据、模型、8093文件、计划任务或服务。

## 程序与复核

- pSpace只读审计：[audit_pspace_top4_hcz_aug9.py](../../tools/audit_pspace_top4_hcz_aug9.py)
- 幂等提交与回读：[remote_submit_hcz_aug9_upward_label.ps1](../../tools/remote_submit_hcz_aug9_upward_label.ps1)
- 顶温专项报告：[HCZ上移事件平均顶温对比_20260811.md](../HCZ上移事件平均顶温对比_20260811.md)

当前8892服务器证据哈希覆盖其既有98变量盲回放上下文；四点顶温的pSpace直读结果保存在标签备注与独立审计哈希中。后续若需要把四点顶温也纳入服务器`source_context`的结构化字段，应作为单独版本化改造，不能重写本条追加记录。
