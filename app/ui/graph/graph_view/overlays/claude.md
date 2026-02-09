# ui/graph/graph_view/overlays 目录

## 目录用途
存放 `GraphView` 级别的叠层绘制组件，例如小地图与标尺叠层，负责在视图坐标系中渲染辅助可视化而不修改场景数据。

## 当前状态
- `minimap_widget.py`：
  - `MiniMapWidget`：嵌在 `QGraphicsView.viewport()` 右下角的小地图组件，展示整个节点图的缩略图，并叠加当前视口矩形。
  - 场景边界缓存 `_cached_scene_rect`：
    - 常规图：通过 `scene.itemsBoundingRect()` 估算内容边界，并在缓存重建时更新（避免每帧计算）。
    - 超大图（节点/连线超过阈值）：改为基于 `GraphModel.nodes[*].pos` 估算边界，避免 `itemsBoundingRect()` 对全量图元的遍历成本。
  - 渲染缓存 `_cached_scene_pixmap`：
    - 常规图：使用 `scene.render(...)` 生成缩略图（更精确）。
    - 超大图：降级为"模型级点阵渲染"（仅绘制节点分布，不渲染连线与复杂样式），避免 `scene.render(...)` 在超大图下触发全量遍历造成卡顿。
  - 监听 `scene.changed/sceneRectChanged` 合并触发缓存重建；采用**尾缘防抖**策略，且会根据图规模自动加大防抖间隔，拖动或批量修改期间只在停止操作后重建一次缓存。
  - 小地图内支持左键点击或拖动来跳转视口位置，坐标换算与 `paintEvent` 中的缩放/偏移逻辑保持一致，保证显示与交互一致性。
- `ruler_overlay_painter.py`：
  - `RulerOverlayPainter`：以静态方法在 `GraphView.paintEvent` 中绘制顶部/左侧坐标标尺，基于 `viewportTransform` 计算每单位像素并自适应合并刻度，即使极小缩放也能自动增大间隔避免文字堆叠；标尺文字的等宽字体由 `app.ui.foundation.fonts` 统一选择，避免硬编码平台字体名。
  - 在视图坐标系中绘制，对场景缩放和平移透明，保证标尺刻度与屏幕像素对齐。
  - 左上角交叉区域会显示当前缩放百分比（如 `100%`），用于在缩放/适配全图/动画聚焦时快速确认当前倍率。
- `graph_search_overlay.py`：
  - `GraphSearchOverlay`：画布内搜索浮层（Ctrl+F 呼出），支持实时匹配并批量高亮命中节点、灰显非命中元素。
  - 搜索输入采用**尾缘防抖**（默认 120ms），避免每个字符都触发全图匹配/灰显/列表重建导致卡顿。
  - 提供"上一个/下一个"导航与镜头聚焦；为保证超大图下的跳转响应速度，搜索导航默认禁用平滑动画（仍复用 `GraphView.focus_on_node` 的聚焦口径）。
  - 搜索栏挂载在 `GraphView` 本体（viewport 的兄弟层）上，并在定位时以 `viewport.geometry()` 为基准自动避开坐标标尺区域（顶部/左侧），避免 viewport 像素滚动优化导致叠层"跟着画布移动"，同时确保缩放与重绘时不会被标尺覆盖而"看起来消失"。
  - 搜索支持匹配 **GIA序号**（导出到 `.gia` 时的从 1 开始稳定序号），并在结果列表摘要与 tooltip 中展示，便于按"导出序号"快速定位节点。
  - 默认分页大小为 5 条/页；当查询为纯数字时，会优先将 `GIA序号==该数字` 的节点排在结果最前。
  - 当查询有结果时会自动展开"结果列表"，无结果时自动收起；也支持通过"展开/收起"按钮手动控制，或在搜索框按 ↓ 展开并聚焦列表；展开按钮箭头与列表状态保持同步。
  - 结果列表支持"命中原因可视化"：列表项会显示**命中字段标签 + 命中片段**，并在标题/命中片段中高亮命中的关键字，便于快速判断"为什么命中"。
  - 结果列表按页按需构建当前页 UI 项；分页模式下提供上一页/下一页/页码，避免命中大量节点时一次性渲染过多项造成卡顿。
  - 结果列表项使用 `setItemWidget(...)` 自绘三行富文本：为避免 delegate 额外绘制 `QListWidgetItem.text` 造成重影，item 本身不设置可见文本。
  - 结果列表项高度由 `_result_item_height_px()` 统一估算并缓存：基于 `QFontMetrics.lineSpacing()` + safety padding，避免部分中文字体/缩放下行高偏小导致每行文本被裁切。
- `graph_perf_overlay.py`：
  - `GraphPerfOverlay`：画布性能面板（由设置开关控制，默认关闭），在画布左上角显示拖拽/缩放/重绘的耗时分解，并提示最大开销段，辅助定位超大图平移卡顿来源。
  - `GraphPerfMonitor`：轻量滚动窗口采样器：
    - 低频段（view/overlay/controller）可直接记录耗时；
    - 高频段（item paint/shape 等）采用**按帧聚合**（sum+count→每帧写入一次 series），并追踪"上一帧最慢 N 个图元"，避免引入重度 profiler 的额外抖动。
    - 计数与耗时分离：支持在面板中同时展示"耗时分解 + 上一帧调用次数/绘制数量"。
    - 帧快照：保留"上一帧各段 ms 汇总"（包含 record_ms 与按帧聚合段），用于计算 `view.paint.scene` 中未被细分项覆盖的**未归因开销**。
    - 拖拽快照：额外保留"最后一次 panning 帧"的快照（耗时/次数/最慢图元），便于松手后仍可复制到拖拽时的分解数据。
  - 面板布局：高度按固定行数估算并随窗口可用空间裁剪，避免频繁依赖 `sizeHint()` 导致的抖动与额外布局成本。
  - 复制与交互：支持"复制"按钮一键复制整段文本，也支持鼠标选择并 `Ctrl+C` 复制；右键/中键与滚轮事件默认放行给画布，以便在面板区域也能平移与缩放；面板作为 `GraphView` 的直接子控件以规避 viewport.scroll 的像素搬运。
  - 统计口径提示：
    - 面板新增 `未归因(last)=scene-已统计`：近似反映 Qt 内部 item 枚举/排序/状态保存等 C++ 开销（不在 Python 插桩内）。
    - 面板新增 `panning(last)`：展示"最后一次拖拽帧"的最大开销段、未归因开销、panning 下的 paint calls 与最慢图元。

- `graph_loading_overlay.py`：
  - `GraphLoadingOverlay`：GraphView 的通用加载遮罩（view 的直接子控件，覆盖整个 view 而非 viewport），用于长任务期间提供状态文案/进度并阻断交互（避免后台计算期间模型被修改导致线程不安全）。
  - 组件由外部控制器驱动：`show_loading(title, detail, progress_value, progress_max, cancelable, on_cancel)` / `set_progress` / `set_detail_text` / `hide_loading`；默认使用不确定进度（busy bar），可按需切换到确定进度。
  - 样式与主题：复用 `ThemeManager` 的 token（卡片背景/边框/文本色），遮罩背景为半透明黑以保留“仍在当前画布处理”的上下文感；取消按钮仅在 `cancelable=True` 时显示，并通过保存的 handler 回调触发（避免重复连接导致多次触发）。

- `pan_freeze_overlay.py`：
  - `PanFreezeOverlay`：画布平移期间的"全场景快照"覆盖层（用于在超大图上获得极致拖拽流畅度；缩放冻结由 `ZoomFreezeOverlay` 单独处理）。
  - **双层缓存机制**：
    - **全场景低清缓存**：将整个节点图渲染为一张受上限约束的全场景位图（最大 4096px），用于保证平移/缩放期间“永远有内容、不空白”。
      - 使用 `scene.itemsBoundingRect + scene.render(...)` 生成（更接近真实渲染）；在超大图下可能因降采样而偏糊，但保证“有内容可参考”。
    - **视口周边高清缓存**：仅渲染“当前视口附近的一大块区域”（默认约 \(1.7\times\) 视口的 sceneRect 宽高，并按视口像素尺寸自动限幅），像素密度以当前 view 缩放为基准（近似 \(view\_scale \times devicePixelRatio\)），用于保证冻结期间节点标题/端口等信息仍可读。
    - **绘制顺序**：先铺全场景低清缓存，再将局部高清缓存按重叠区域叠加绘制，最后补绘标尺；绘制路径仍保持 `fillRect + drawPixmap(+drawPixmap) + ruler` 的常数级开销。
      - 为避免全局低清被放大后呈现“块状马赛克”，全局底图绘制会单独开启 `SmoothPixmapTransform` 使其更像“模糊打底”；局部高清层仍保持关闭平滑以保证锐利。
  - **层级设计**：父控件为 viewport（与 MiniMapWidget 同级），使 `minimap.raise_()` 能正确将小地图置于覆盖层之上；view 级子控件（SearchOverlay/PerfOverlay/TopRightButtons）自然位于 viewport 之上，无需额外处理。冻结期间 GraphView.paintEvent 不运行（NoViewportUpdate），标尺由覆盖层通过 `RulerOverlayPainter.paint()` 自行补绘。
  - **缓存生命周期**：监听 `scene.changed` 信号，场景内容变化时仅标记缓存为脏（不做自动重建避免卡顿）；缓存仅在 `begin_freeze()` 且 pixmap 为空时同步重建，若缓存存在但已脏则直接使用旧缓存以避免冻结启动延迟。
  - **局部高清缓存重建策略**：仅在 `begin_freeze()` 入口按需构建/切换（例如视口跑出覆盖范围、缩放或 DPI 变化），交互过程中仅触发 repaint，不做 `scene.render(...)`，避免拖拽/滚轮期间卡顿。
  - 平移静态快照：由 `settings.GRAPH_PAN_FREEZE_VIEWPORT_ENABLED` 控制；平移开始时显示覆盖层，同时将视图更新模式切到 `NoViewportUpdate`，拖拽过程中从全场景缓存裁剪绘制以避免每帧重绘大量 items；松手后隐藏覆盖层并恢复真实渲染。
  - 覆盖层对鼠标事件透明，不阻断 `ScrollHandDrag`；绘制路径保持 `fillRect + drawPixmap + ruler` 的常数级开销，并默认关闭 `SmoothPixmapTransform` 以降低重采样成本（全局底图绘制会按需单独开启平滑，以改善“黑方块”观感）。

- `zoom_freeze_overlay.py`：
  - `ZoomFreezeOverlay`：滚轮缩放期间的“视口快照”覆盖层。
  - begin 时抓取一次当前 viewport 图像（不含 MiniMap/右上角控件等子控件），缩放过程中按交互控制器累计的“相对缩放因子”在 viewport 坐标系内绕 pivot（鼠标位置）对该快照做仿射变换绘制（不对 view 做逐步 scale）。
  - 视口快照像素尺寸会做上限约束（默认 2048px），避免高分辨率窗口下抓图过大导致缩放起手卡顿或每步重绘过重。
  - 设计目标：缩放期间避免 `scene.render(...)` 与全量 item 重绘，提供更丝滑的滚轮缩放体验；停止滚轮后由真实渲染快速补齐新内容与细节。
  - 性能取舍：缩放预览期间只绘制缩放后的快照（不额外补绘标尺），进一步降低高频滚轮事件下的 per-frame Python 绘制开销；滚轮停止后由真实渲染恢复标尺与其它叠层。

## 注意事项
- 小地图的场景缓存重建是**异步且防抖的**：频繁拖动画布或节点时不会每次都立即重建缓存，而是在操作结束后短暂延迟一次刷新，小幅牺牲实时性换取大幅减小大图下的卡顿。
- `MiniMapWidget` 通过 `GraphView.mini_map.update_viewport_rect()` 与 `ViewAssembly.update_mini_map_position()` 跟随视图滚动与尺寸变化，仅在视口矩形或位置变化时请求局部重绘，不重新渲染场景内容。
- 叠层组件只负责渲染与交互，不直接修改底层 `GraphModel` 或 `GraphScene`；需要修改模型时应通过控制器层或场景命令完成。
- 叠层绘制的背景色、网格线色与标尺文本颜色统一来自 `ThemeManager.Colors` 中的画布标尺 token，深浅主题切换时可在 token 层集中调整，避免在各处重复改写。
- `PanFreezeOverlay` 的全场景缓存独立于 `MiniMapWidget` 的缩略图缓存：前者分辨率更高（最大 4096px）用于平移/缩放期间替代真实渲染，后者低分辨率（200×150）仅用于小地图缩略显示。
- `PanFreezeOverlay` 的父控件为 viewport（与 MiniMapWidget 同级），确保 `raise_()` 在两者之间有效；当 `NoViewportUpdate` 生效时 Qt 不会调用 `viewport.scroll()`，因此 viewport 的子控件不会被物理滚动偏移。
- `PanFreezeOverlay` 不做自动缓存重建（`_on_scene_changed` 仅标脏），避免"恢复真实渲染后 scene.changed 密集触发 → 后台 scene.render() 全图重渲染"导致的卡顿；缓存在下次冻结开始时按需重建。
 - `ZoomFreezeOverlay` 只覆盖滚轮缩放的短交互窗口：缩放期间不展示“视口外的新区域”，但能极大降低滚轮每步的重绘开销；滚轮停止后由控制器统一补齐背景与叠层联动刷新。
