# ui/overlays 目录

## 目录用途
存放场景叠加渲染相关的 Mixin 组件,用于从 `GraphScene` 中分离渲染职责。

## 当前状态
- `scene_overlay.py`：
  - `SceneOverlayMixin`：负责网格背景、基本块、Y 调试图标、链路序号徽标等叠加渲染。画布叠层使用 `ui/graph/graph_palette.py` 中的固定深色调色板（如徽标背景 `#FFAA00/#FFD400`、描边黑/白），不随主题切换，保持节点图画布的既定视觉。
  - 核心方法包括 `drawBackground/drawForeground`、`_draw_block_label`、`_draw_text_with_stroke`、`_draw_non_overlapping_label_grid` 等。
  - 性能插桩：当宿主场景挂载 `_perf_monitor`（由画布性能面板启用）时，会在 `drawBackground/drawForeground` 记录网格与叠层绘制耗时分解，辅助定位超大图平移卡顿的主要开销段；默认不挂载时零开销。
  - `_ensure_layout_y_debug_info`：在需要时**只进行一次**临时布局计算以生成 `_layout_y_debug_info`；若布局结果未产生调试信息，会基于 `LayoutContext` 与 `find_event_roots/has_flow_edges` 输出一条结构化日志，包含图名、节点/边数量、是否存在流程边、事件起点数量以及分类结果（纯数据图 / 仅含流程但无事件起点 / 存在事件起点但调试写入为空），并预览前若干个事件起点，帮助快速判断当前图被视作“事件流图”还是“纯数据图”，同时避免反复重试导致控制台刷屏。
  - Y 调试图标绘制优化：在 `drawForeground` 中先收集可见图标矩形，再分两趟批量绘制（圆形背景→"!" 文本），避免在循环内反复 `setPen/setBrush/setFont`，降低大图拖拽时的 per-icon 绘制开销。
  - LOD：当 `settings.GRAPH_LOD_ENABLED=True` 且缩放低于“节点细节阈值”时，Y 调试“!”图标与链路徽标会自动隐藏，并清空 `_ydebug_icon_rects` 命中映射，避免在鸟瞰视角产生噪音与额外绘制/命中成本。
  - 交互降级：当宿主场景设置 `_view_panning=True` 且 `settings.GRAPH_PAN_HIDE_ICONS_ENABLED=True`（由视图交互控制器在平移/缩放开始/结束时同步）时，`drawForeground` 会视为低细节模式并跳过 YDebug 图标/链路徽标等调试叠层绘制，同时清空 `_ydebug_icon_rects`，保证交互期间“不可见即不可点”且更流畅。
  - 网格开关与交互优化：当 `settings.GRAPH_GRID_ENABLED=False` 时 `drawBackground` 仅绘制纯底色，不绘制网格线；此外交互期间（`_view_panning=True`）也会跳过网格线绘制（保留底色）以降低背景每帧重绘开销。
  - 画布网格 LOD：`drawBackground` 会根据缩放自动放大网格间距（保证网格线在屏幕像素上不过密），避免低倍率下的噪音与绘制开销；常规模式使用 `settings.GRAPH_GRID_MIN_PX`，鸟瞰模式使用更激进的 `settings.GRAPH_BLOCK_OVERVIEW_GRID_MIN_PX`。
  - basic blocks 边界矩形：按 `node_item.sceneBoundingRect()`（并合并 `childrenBoundingRect()`）计算并缓存，避免每帧全量扫描；拖拽节点时对受影响块做增量扩张以保持跟随，拖拽结束或节点重布局后标记为 dirty 并在下一次背景绘制时重算矩形（可收缩、可覆盖可变高度节点）。
  - 鸟瞰模式（仅显示块颜色）：当宿主场景开启 `blocks_only_overview_mode=True` 时：
    - `drawBackground` 仍绘制画布背景（底色+网格），并使用更大的最小像素网格间距以进一步降噪提速；
    - 即使 `settings.SHOW_BASIC_BLOCKS=False`，也会绘制 basic blocks（避免鸟瞰视角画布空白）；
    - `drawForeground` 不再绘制块编号标签，同时视为低细节模式，避免绘制 Y 调试图标/链路徽标等噪音。

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

