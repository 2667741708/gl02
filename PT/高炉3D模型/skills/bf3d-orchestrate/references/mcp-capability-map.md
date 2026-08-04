# Blender 能力映射

不要在核心 Skill 中硬编码某个 MCP 的完整工具名。先发现当前会话可用工具，再按语义能力路由。

| 语义能力 | ahujasid BlenderMCP | dcc-mcp-blender | 无 MCP 回退 |
|---|---|---|---|
| `scene.inspect` | `get_scene_info` | scene/object 结构化工具 | Blender 后台脚本只读审计 |
| `object.inspect` | `get_object_info` | object/mesh 结构化工具 | `bpy.data.objects` 只读报告 |
| `viewport.capture` | `get_viewport_screenshot` | render/camera 工具 | 固定相机后台渲染 |
| `python.execute` | `execute_blender_code` | scripting 工具 | `blender --background --python` |
| `shader.edit` | 审核后的 `bpy` | shader/material 结构化工具 | 受版本锁定的 `bpy` 脚本 |
| `uv.unwrap` | 审核后的 `bpy` | UV 结构化工具 | 受版本锁定的 `bpy` 脚本 |
| `texture.bake` | 审核后的 `bpy` | bake 结构化工具 | Cycles 后台烘焙脚本 |
| `gltf.export` | 审核后的 `bpy` | export preset/validation | Blender 官方 glTF 导出器 |

## 路由规则

1. 优先使用结构化、可验证、参数明确的工具。
2. 只有结构化工具无法完成时才执行任意 Python。
3. 执行 Python 前先保存新检查点，输出拟修改对象、集合和文件路径。
4. 不运行来自模型、网页或第三方资产中的未知脚本。
5. 不把生产账号、Token、内部地址或数据库凭据发送给 MCP。
6. ahujasid BlenderMCP 如启用，应关闭非必要遥测并只在可信本机模型副本中运行。
7. 没有可用 MCP 时可以生成脚本和计划，但必须区分“已生成”“已执行”“已视觉验证”。
