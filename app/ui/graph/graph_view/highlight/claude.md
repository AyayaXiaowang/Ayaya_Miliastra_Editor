## 目录用途
提供节点图视图层的高亮/灰显服务，在不触碰模型的前提下统一管理节点、连线与端口的视觉状态。

## 当前状态
- `highlight_service.py` 定义静态方法（`highlight_node/edge/nodes_and_edge/clear_highlights/dim_unrelated_items` 等），直接操作场景中的图形项并保持一次性批量更新。
- 服务通过 `GraphView` 注入，仅依赖 `scene()` 暴露的高亮 API，与控制器或模型层完全解耦。
  - 灰显（opacity）支持 **差量更新**：在 `GraphScene` 上缓存上一次的焦点集合与图形项数量，仅对“焦点集合变化”的节点/连线做 `setOpacity`，避免连续交互时反复全量遍历全图。
  - 兼容 fast_preview 的“批量渲染边”：当场景无 per-edge item 时，灰显/选中会委托 `GraphScene.set_batched_dim_state(...)` / `set_batched_selected_edge_ids(...)` 更新批量边层；同时仍会对少量被 materialize 的 `edge_items` 逐个设置 opacity，保证展开节点的端口对齐边也符合灰显状态。
  - `restore_all_opacity` 会在不存在灰显状态时直接短路，减少无意义的重置成本。

## 注意事项
- 调用前需确保 `GraphView.scene()` 存在且图形项索引已构建，否则方法会提前返回，防止访问空引用。
- `highlight_nodes_and_edge` 先清空再批量高亮，可避免逐个调用导致的互相覆盖；调用者如需累积状态，请自行管理。
- 灰显逻辑通过调节 `QGraphicsItem.setOpacity` 实现，不改变选择状态；退出高亮记得调用 `restore_all_opacity`。

