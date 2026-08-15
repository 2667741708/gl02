# 220.12 罐重设定点位登记交接

状态：生产登记完成；最后核对：2026-08-14；追踪编号：
`OPS-SENSOR-REGISTRY-HOPPER-WEIGHT-SET-20260814`。

## 结果

220.12 `bf_sensor.sensor_registry` 已按本机正式点位清单登记 14 条记录：

- 复核并更新 `L_south`、`L_north` 两条现有记录；实际映射仍为
  `SIO_GL02_LD_T0075`、`SIO_GL02_LD_T0076`。
- 新增 11 个物理分量 `Hopper_weight_set_01`～`Hopper_weight_set_11`，对应
  `SIO_GL02_LD_T0115`、`T0116`、`T0117`、`T0119`～`T0126`。
- 新增派生目录项 `Hopper_weight_set`，定义为同一分钟 11 个分量状态之和；
  `SIO_GL02_LD_T0118` 是“9号布料圈数设定”，明确不参与重量求和。

登记器为 [register_hopper_weight_set_points.py](../../tools/register_hopper_weight_set_points.py)，
权威来源为 [点位清单.tsv](../../数据库同步和存取/config/点位清单.tsv)。登记前审计确认
不存在 tag 冲突；登记后 `expected_rows=14`、`registered_rows=14`、`mismatches={}`。

## 生产文件与回滚

- 生产项目：`F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW`。
- 更新后清单 SHA-256：
  `88113DF881046DD1F15F47387657F88EEF0F95CA8B90B5FB5B790E101F99C757`。
- 更新前清单 SHA-256：
  `07A47F245A9ED6E4C21C33B6B6B288499A92A61E1CB3DFF023EF47D59C25EA37`。
- 回滚文件：
  `数据库同步和存取\config\点位清单.tsv.bak_20260814_hopper_registry`；
  其 SHA-256 已与更新前清单一致。
- 上传到用户临时目录的 TSV 已删除；可复用登记器与回滚备份按项目规则保留。

## 采集验收

登记后仅调用一次既有 `sync_from_243_pg.py`，以单 worker 同步上述 11 个物理分量，
没有启动新的常驻 pSpace 读取程序，也没有重启 8093、8768 或 8770：

- `tags_ok=11`、`tags_error=0`；
- 写入 `59` 条分钟值和 `71` 条 raw 值；
- `_01`～`_06` 各有 9 条分钟历史，最新分钟为 14:43；
- `_07`～`_11` 各有 1 条分钟历史，最新分钟为 14:37。

## 尚未完成的运行语义

`Hopper_weight_set` 已成为正式派生目录项，但本轮“登记更新”没有修改现有同步器的派生
物化逻辑，因此它本身尚无 `one_minute_values` 行。页面或查询若要直接使用该总量，下一步应在
现有同步/查询链路中按同一分钟状态前向保持后求和；任一分量缺失时必须标记缺数，不得按 0
参与求和。该实现应复用现有同步程序，不增加 pSpace 通信连接。

## 可复现验证

```powershell
python .\tools\verify_foreman_local_point_catalog.py --root .\数据库同步和存取
python .\tools\register_hopper_weight_set_points.py --root .\数据库同步和存取
```

成功信号：本机清单 `165` 行、`162` 个物理点、`3` 个派生点；生产登记审计为
`14/14` 且无映射差异。
