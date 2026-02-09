## 目录用途
存放图视图层面的交互控制器相关代码，负责节点图视图的键鼠事件分发、拖拽模式切换以及交互期间的性能调优逻辑。

## 当前状态
包含 `interaction_controller.py`，为 `GraphView` 提供统一的交互入口：管理滚轮缩放、画布平移（手抓模式）、框选、节点/连线选择与快捷键处理，并在不同交互阶段动态调整视图的更新模式和缓存策略。
- 在只读视图且开启 `GraphView.enable_click_signals` 的前提下，会将左键单击节点/连线/空白转换为 `graph_element_clicked` 信号，供上层页面（例如任务清单的图预览）做联动高亮与跳转，而不改变编辑模式下的交互行为。
 - 兼容大图快速预览：当场景使用轻量 Edge 图元或"批量渲染边层"（无 per-edge item）时，交互控制器会在 `itemAt` 未命中时走场景的模型级命中（`pick_batched_edge_id_at`），确保只读预览的"连线点击/双击"与跳转信号仍然可用；同时在左键按下阶段也会将批量边命中视为"命中图元素"，避免误进入 RubberBand 框选模式。
- 当 `settings.GRAPH_PERF_PANEL_ENABLED=True` 时，交互控制器会在 `scrollContentsBy` 的后续刷新路径（背景失效/小地图/浮窗定位等）记录耗时分解，供画布性能面板展示与定位卡顿来源。
- 视图交互（平移/缩放）性能模式：在拖拽平移开始/结束时会调用场景的 `set_view_panning(True/False)`，滚轮缩放期间会调用 `set_view_zooming(True/False)` 并带 debounce；当 `settings.GRAPH_PAN_HIDE_ICONS_ENABLED=True` 时，交互期间临时隐藏端口/⚙/+ 并让叠层跳过 YDebug 前景绘制，停止交互后按 LOD 状态恢复，减少大图平移/缩放的 item 枚举与绘制固定开销。
- 拖拽平移静态快照（可选）：当 `settings.GRAPH_PAN_FREEZE_VIEWPORT_ENABLED=True` 时，拖拽平移开始显示全场景缓存覆盖层，同时把视图更新模式切到 `NoViewportUpdate`；拖拽平移过程中从全场景缓存图裁剪当前视口区域绘制（不重绘场景 items），松手后隐藏覆盖层并恢复真实渲染，用于在超大图上获得极致平移流畅度（全场景缓存使得平移中也能看到原本不在视口内的节点）。
- 缩放静态快照（可选）：当 `settings.GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED=True` 时，滚轮缩放开始显示**视口快照**覆盖层（一次抓取当前 viewport 图像，不含子控件），同时把视图更新模式切到 `NoViewportUpdate`；缩放过程中**不对 QGraphicsView 做逐步 scale**，仅更新覆盖层的“绕鼠标位置缩放”预览；滚轮停止（debounce）后将累计倍率一次性应用到 view 并恢复真实渲染，用于让滚轮缩放更丝滑。
 - 取舍：缩放冻结期间仅基于“开始缩放时的视口画面”变换，因此缩放过程中不会出现视口外的新内容；停止滚轮后真实渲染会很快补齐完整细节与新区域。

- 双击复合节点会发射 `jump_to_graph_element`，payload 包含 `composite_id`（优先）与 `composite_name`，供上层跳转并定位到复合节点页面。

## 注意事项
- 交互控制器假定宿主视图为 `QGraphicsView`，且由 `app.ui.graph.graph_view.GraphView` 持有并转发事件。
- 键盘事件拦截需尊重"文本输入/文本编辑"焦点：当 `scene.focusItem()` 为可交互的 `QGraphicsTextItem`（或焦点位于 `QGraphicsProxyWidget` 内嵌的 `QLineEdit/QTextEdit` 等）时，应让控件自行处理复制/粘贴/撤销/删除等按键，避免图级快捷键吞掉用户的文本操作。
- 拖拽和平移逻辑会临时修改视图的缓存模式、视口更新模式与渲染提示，以平衡大图性能与视觉效果，恢复逻辑必须始终成对调用。
- 与布局 Y 调试、小地图、标尺等模块存在协作关系，修改交互行为时需要兼顾这些覆盖层的更新与位置同步。
- 布局 Y 调试"!"图标的点击拦截仅对左键生效，避免右键/中键平移在图标区域被误拦截导致无法进入手抓模式。
- 右键/中键平移阶段会关闭高成本渲染提示，并临时禁用 `CacheBackground` 以避免网格在部分 Windows 环境下出现"分块错位/残影"；同时按缩放比例节流叠层更新，每次结束平移后会立即补齐小地图、悬浮层与 Y 调试卡片的位置。
- `GraphSearchOverlay` 作为 `GraphView` 的直接子控件（不是 viewport 子控件），因此不会被 `viewport.scroll` 的像素滚动优化带走；滚动路径无需为其做额外 update/raise 处理。
- 为保证"右键/中键/空格手抓"在节点/连线之上也能稳定启动，平移期间会临时设置 `view.setInteractive(False)`，避免伪造左键 press 被图形项优先吃掉导致无法进入 `ScrollHandDrag`。
- 缩放、滚动与节流判断路径都会主动调用 `_reposition_ydebug_tooltip`，确保调试卡片始终贴合其场景锚点。
- 滚轮事件在"转发到 Tooltip 卡片子控件"时会重建 `QWheelEvent` 并派发；注意部分 PyQt6 构建的 `QWheelEvent` 不包含 `source()`，转发构造需使用兼容签名（不依赖 `source`）。
- 左键交互（节点拖拽、RubberBand 框选、端口连线预览）期间会暂时关闭背景缓存；常规编辑场景使用 `FullViewportUpdate` 规避残影，而在超大图/快速预览（`fast_preview_mode`）下保持 `MinimalViewportUpdate` 以降低拖拽卡顿；释放后由控制器统一恢复原有刷新与缓存策略。
- 交互层对节点/连线图形项的引用应从 `app.ui.graph.items.*` 直接导入，避免依赖 `graph_scene` 的"再导出"名称（以免在运行时缺失导致 ImportError）。
