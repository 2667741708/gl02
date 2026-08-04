# 高炉 3D 资产登记入口

当前机器可读登记表为 [bf3d_asset_registry.v1.json](./bf3d_asset_registry.v1.json)。

资产状态口径：

- `integrated`：已经进入当前受控母版并具有独立导出物。
- `integrated_via_v5`：通过锁定 V5 静态结构进入母版。
- `registered_deferred`：已预留模块集合，但尚未选定唯一受控来源，不参与 R1 导出。
- `master_only`：只用于 Blender 组织或审查，不进入运行 GLB。

R1 母版为候选资产，不替换 `高炉前端数据/models/gl02_blast_furnace.glb`，也不授权生产 8092 路由切换。

## 分布式模型资产库

面向人工浏览和直接取用的一资产一目录归档位于：

- [模型资产库](../模型资产库/README.md)
- [机器可读资产目录](../模型资产库/asset_catalog.v1.json)

原 `bf3d_asset_registry.v1.json` 继续承担受控母版与模块状态登记；新资产库负责把
当前可用模型、网页预览和来源说明放在同一目录中。两者角色不同，不互相覆盖。
