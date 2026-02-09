## 目录用途
- 存放“长连线中转节点（获取局部变量）插入器”的实现代码：在跨块复制完成后，对超阈值的长距离数据边插入 relay 节点并重写连线，保证排版稳定与可读。

## 当前状态
- `inserter.py`：核心入口 `insert_local_variable_relays_after_global_copy(...)`（布局增强阶段调用）；会为 relay 节点写入 `GraphModel.metadata.port_type_overrides`（覆盖 `值` 输出端口的具体类型），用于链路类型传播与 UI 展示。
- relay 节点创建时会同步填充 `NodeModel.node_def_ref`（builtin + canonical key），保证后续 UI/导出/自动化链路可稳定解析 NodeDef（不依赖 title）。
- `cleanup.py`：在重建前清理既有 relay 结构并尽量恢复原始长边；同步清理 stale relay 的 `port_type_overrides` 条目，避免残留污染后续推断。
- `ids.py`：relay node_id/edge_id 的稳定前缀与解析工具（含 slot 编码）；作为稳定 import 入口供上层复用。

## 注意事项
- 不吞异常；结构不一致应直接抛出以暴露建模或规则问题。
- id 必须确定性（不使用 uuid），保证多次自动排版幂等且结果稳定。
- 局部变量 relay 只在类型约束允许时插入；对字典/泛型字典等必须跳过。
- relay 节点属于布局增强基础设施：类型覆盖仅服务于展示/推断，应随“清理→重建”过程同步维护，禁止长期累积不清理。


