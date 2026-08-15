# 模型响应与 ABC33 上下文映射

## Prompt 顺序

公共前缀固定为：身份、安全边界、回答规则、固定工艺规则。随后才追加单个炉框的 `abc_rule_explanation_context.v1` 和本次问题。公共前缀稳定可让支持前缀缓存的运行时复用相同 attention/KV 计算；这不是人为固定“注意力分数”，也不保证每次一定命中缓存。

## 事实边界

- `rule/calculation/process_guidance` 是服务端权威事实，模型不得修改。
- `context_hash` 标识准确快照；回答消息通过 `qa_message_context_snapshots` 绑定当时快照。
- 知识库证据仍由 keyword 链路按需注入；没有证据时必须明确，不得补造。
- 首轮结果按上下文、Prompt 版本和模型缓存；普通追问仍作为新消息生成。

当前弹窗展示确定性计算结构和模型文本；后续若升级为严格结构化模型 JSON，必须保持字段白名单、term_id 引用校验和 C 类安全提示校验。
