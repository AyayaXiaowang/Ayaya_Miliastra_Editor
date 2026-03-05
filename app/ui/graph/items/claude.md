## 目录用途
`app/ui/graph/items/`：节点图编辑器的图形项实现（`QGraphicsItem` 等），负责节点/端口/连线与少量辅助图元的渲染与交互，并与 `GraphScene` 的模型/命令系统协作。

## 当前状态
- **基础图元**：`NodeGraphicsItem`（`node_item.py` + mixin 拆分）、`PortGraphicsItem`（`port_item.py`）、`EdgeGraphicsItem`（`edge_item.py`）构成画布主元素。
- **布局一致性**：端口布局与输入行规划复用 `engine.layout.utils.graph_query_utils.build_input_port_layout_plan`，确保 UI 与布局层高度估算/换行策略一致。
- **常量与类型展示**：行内常量控件统一由 `app.ui.widgets.constant_editors` 创建；端口“⚙ 类型气泡”通过 `port_type_resolver` 解析展示级有效类型，并与自动化侧共享同一套 EffectivePortTypeResolver 口径。
- **事件节点诊断**：当 `node_def_ref.kind="event"` 时，端口 tooltip 会附带 `event_key/mapped_builtin_key` 与映射命中状态（hit/miss），便于定位 event 映射口径与缺口原因。
- **大图性能路径**：支持 LOD（按缩放隐藏端口/文字/连线命中）、行内常量控件虚拟化（占位→按需 materialize→释放）、邻接索引驱动的局部连线刷新；fast preview 模式提供轻量节点/边图元，并可选“批量边层”降低 item 数量。
- **批量边层与插桩**：`batched_edge_layer.py` 在只读/fast preview 场景将大量边合并为单一图元绘制；性能面板启用时，图元在 `paint/shape` 等高频路径按帧聚合采样，便于定位卡顿来源。

## 注意事项
- 图形项不直接写盘、不直接改 `GraphModel`；模型变更必须走 `GraphScene` 命令/控制器，保证撤销栈一致。
- 避免循环导入：类型标注用 `TYPE_CHECKING`，依赖场景能力通过 `self.scene()` 获取。
- LOD/虚拟化/批量边属于性能策略：阈值与组合判定以 `settings` 与 `app.runtime.services.graph_scene_policy` 为单一真源。
