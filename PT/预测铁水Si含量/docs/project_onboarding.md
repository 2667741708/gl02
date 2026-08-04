# 项目入门

## 目标

使用有工艺意义的语义神经元，将传感器时序、炉况诊断、前序炉化验和经过谱系
确认的炉料成分转换为可解释、可校准的铁水Si预测分布。

## 当前完成

- 独立项目目录；
- 第一版思想、架构和数据边界；
- 纯Python推理内核；
- 未标定状态门；
- Si正态残差分布和目标带概率；
- V1固定切分与6模型训练；
- `±0.05`主验收及21组扩展神经元代理实验；
- 130点长表30/60/120/240分钟时序派生器；
- 单元测试与双次确定性复现；
- MES正式meltno标签合同与三类目标门禁；
- 133物理点的当前值、60/120分钟变化量和斜率正式炉次数据集；
- 2,291炉正式代表Si与整炉Si分布离线训练；
- 论文初始书目。

## 当前未完成

- MES真实取样时间、铁口编号和出铁阶段数据补齐；
- 30/240分钟完整窗口统计与炉料/炉渣精确谱系；
- 滞后时间标定；
- 跨月滚动时间外回测和分布校准；
- 影子运行；
- MCP接口与图表。

## 推荐阅读顺序

1. [README](../README.md)
2. [想法001](../ideas/001_有意义神经元的Si预测思想.md)
3. [架构](architecture.md)
4. [需求追踪](requirements_traceability.md)
5. [正式标签合同](data_contract.md)
6. [V3实验方法](experiment_method_v3.md)
7. [三轮实验总结与混合网络路线](experiment_summary_and_hybrid_roadmap.md)
8. [问题追踪](question_traceability.md)
9. [程序索引](program_index.md)
10. [测试参考](test_reference.md)
11. [论文目录](../papers/README.md)

## 主要入口

- 推理内核：[engine.py](../src/si_semantic_engine/engine.py)
- 命令行：[cli.py](../src/si_semantic_engine/cli.py)
- 设计拓扑：[semantic_neurons.design.json](../configs/semantic_neurons.design.json)
- 正式标签合同：[si_label_contract.v3.json](../configs/si_label_contract.v3.json)
- V3数据构建：[build_formal_si_dataset_v3.py](../../../tools/build_formal_si_dataset_v3.py)
- V3训练：[train_v3.py](../src/si_semantic_engine/train_v3.py)
- 测试：[test_engine.py](../tests/test_engine.py)
