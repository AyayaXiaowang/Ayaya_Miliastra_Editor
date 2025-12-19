# ui/overlays 目录

## 目录用途
存放场景叠加渲染相关的 Mixin 组件,用于从 `GraphScene` 中分离渲染职责。

## 当前状态
- `scene_overlay.py`：
  - `SceneOverlayMixin`：负责网格背景、基本块、Y 调试图标、链路序号徽标等叠加渲染。画布叠层使用 `ui/graph/graph_palette.py` 中的固定深色调色板（如徽标背景 `#FFAA00/#FFD400`、描边黑/白），不随主题切换，保持节点图画布的既定视觉。
  - 核心方法包括 `drawBackground/drawForeground`、`_draw_block_label`、`_draw_text_with_stroke`、`_draw_non_overlapping_label_grid` 等。
  - `_ensure_layout_y_debug_info`：在需要时**只进行一次**临时布局计算以生成 `_layout_y_debug_info`；若布局结果未产生调试信息，会基于 `LayoutContext` 与 `find_event_roots/has_flow_edges` 输出一条结构化日志，包含图名、节点/边数量、是否存在流程边、事件起点数量以及分类结果（纯数据图 / 仅含流程但无事件起点 / 存在事件起点但调试写入为空），并预览前若干个事件起点，帮助快速判断当前图被视作“事件流图”还是“纯数据图”，同时避免反复重试导致控制台刷屏。

- `text_layout.py`：
  - `GridOccupancyIndex`：按行高分桶缓存已占用矩形，支撑文本避让（O(N²)→O(N×桶内数量)）。

- `node_detail_overlay.py`：
  - `NodeDetailOverlay` / `NodeDetailOverlayManager`：在视图左右角展示远距离节点副本，带端口高亮、淡入淡出与节流更新；供 `GraphView` 与只读预览复用。
  - 端口采集直接复用 `NodeGraphicsItem.iter_all_ports()/get_port_by_name()`，不在浮窗内部手写 `_ports_in/_ports_out` 遍历，避免与场景高亮逻辑重复。

## 注意事项
- Mixin 不导入 `GraphScene`,仅假设宿主提供 `model`, `node_items`, `edge_items`, `grid_size` 等属性。
- 叠加渲染、文本避让与节点详情浮窗各自独立，保持最小耦合，便于任务清单与编辑器共用。
- 所有文本绘制使用缓存路径降低 `addText` 调用频率；浮窗组件只处理 UI 呈现，不负责节点加载。
- 叠加文字字体：默认字体统一通过 `app.ui.foundation.fonts` 选择与构造，避免硬编码平台字体族名导致跨平台缺字或告警。
- 涉及链路高亮徽标与调试图标的前景/背景颜色应统一复用 `ThemeManager.Colors` 中的语义色（如 `ACCENT`、`BG_MAIN` 等），避免在叠加层中直接写死十六进制颜色，确保与深色画布和整体主题风格一致。
- 调试类输出仅在缺失 `_layout_y_debug_info` 时触发一条结构化日志，包含必要统计字段，避免在正常编辑流程中刷屏。

