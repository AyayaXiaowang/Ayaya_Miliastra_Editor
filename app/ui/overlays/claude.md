## 目录用途
`ui/overlays/` 存放场景/视图级叠加渲染相关组件，用于从 `GraphScene` 中分离“叠层绘制、文本避让、节点详情浮窗”等纯渲染职责。

## 当前状态
- **场景叠层绘制**：`scene_overlay.py` 提供 `SceneOverlayMixin`，负责 `drawBackground/drawForeground` 中的网格背景、basic blocks 与调试徽标/图标绘制；支持 LOD 与“平移/缩放期间降级绘制”，并可选接入 `_perf_monitor` 记录绘制耗时。YDebug 叠层仅消费 `GraphModel._layout_y_debug_info` 等缓存，不在绘制路径触发布局计算。
- **文本避让索引**：`text_layout.py` 提供 `GridOccupancyIndex`，用于标签/徽标的矩形占用缓存与快速避让。
- **节点详情浮窗**：`node_detail_overlay.py` 提供 `NodeDetailOverlay/NodeDetailOverlayManager`，在视图角落展示远距离节点的只读副本，并复用 `NodeGraphicsItem` 的端口枚举接口实现高亮。

## 注意事项
- Mixin 不导入 `GraphScene`，仅假设宿主提供必要属性（如 `model/node_items/edge_items/grid_size`）。
- 叠层组件只负责绘制与轻量交互，不修改 `GraphModel`。
- 画布相关配色应统一来自 `ui/graph/graph_palette.py` 或 `ThemeManager` token，避免散落硬编码色值。
- 调试日志应限流，避免在正常编辑流程刷屏；异常不做 `try/except` 吞掉。
- YDebug 等诊断输出需受 `settings.GRAPH_UI_VERBOSE` 控制，避免默认刷屏。

