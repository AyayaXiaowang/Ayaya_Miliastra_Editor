# ui/graph/graph_view/overlays 目录

## 目录用途
存放 `GraphView` 级别的叠层绘制组件，例如小地图与标尺叠层，负责在视图坐标系中渲染辅助可视化而不修改场景数据。

## 当前状态
- `minimap_widget.py`：
  - `MiniMapWidget`：嵌在 `QGraphicsView.viewport()` 右下角的小地图组件，展示整个节点图的缩略图，并叠加当前视口矩形。
  - 通过 `GraphScene.itemsBoundingRect()` 计算节点内容边界并缓存为 `_cached_scene_rect`，仅在缓存重建时更新，避免每帧计算。
  - 使用 `_cached_scene_pixmap` 作为场景渲染缓存；监听 `scene.changed/sceneRectChanged`，通过 100ms **尾缘防抖** 合并重建请求：拖动或批量修改期间只在停止操作后重建一次缓存，避免频繁全图渲染导致卡顿。
  - 小地图内支持左键点击或拖动来跳转视口位置，坐标换算与 `paintEvent` 中的缩放/偏移逻辑保持一致，保证显示与交互一致性。
- `ruler_overlay_painter.py`：
  - `RulerOverlayPainter`：以静态方法在 `GraphView.paintEvent` 中绘制顶部/左侧坐标标尺，基于 `viewportTransform` 计算每单位像素并自适应合并刻度，即使极小缩放也能自动增大间隔避免文字堆叠；标尺文字的等宽字体由 `app.ui.foundation.fonts` 统一选择，避免硬编码平台字体名。
  - 在视图坐标系中绘制，对场景缩放和平移透明，保证标尺刻度与屏幕像素对齐。

## 注意事项
- 小地图的场景缓存重建是**异步且防抖的**：频繁拖动画布或节点时不会每次都立即重建缓存，而是在操作结束后短暂延迟一次刷新，小幅牺牲实时性换取大幅减小大图下的卡顿。
- `MiniMapWidget` 通过 `GraphView.mini_map.update_viewport_rect()` 与 `ViewAssembly.update_mini_map_position()` 跟随视图滚动与尺寸变化，仅在视口矩形或位置变化时请求局部重绘，不重新渲染场景内容。
- 叠层组件只负责渲染与交互，不直接修改底层 `GraphModel` 或 `GraphScene`；需要修改模型时应通过控制器层或场景命令完成。
- 叠层绘制的背景色、网格线色与标尺文本颜色统一来自 `ThemeManager.Colors` 中的画布标尺 token，深浅主题切换时可在 token 层集中调整，避免在各处重复改写。

