## 目录用途
封装 `GraphView` 的装配逻辑：在 `setScene`、`resizeEvent` 等关键节点中创建/更新小地图、节点详情浮窗与右上角控件，保证视图组件协同工作。

## 当前状态
- `view_assembly.py` 暴露 `ViewAssembly.attach_scene/on_resize/update_mini_map_position` 三个静态方法，由 `GraphView` 与控制器按需调用。
- 组件初始化顺序：先更新场景矩形（委托场景的 `_update_scene_rect()`：以 `itemsBoundingRect()` 为基础并按视口大小补齐边距，避免超大图按内容倍数扩张导致 `sceneRect` 过大）、再创建 `NodeDetailOverlayManager`、最后构建/定位小地图，避免窗口尺寸尚未稳定时就刷新叠层。
- 右上角按钮定位统一交由 `TopRightControlsManager`，本目录仅负责在 resize 阶段调用其更新接口，并确保布局 Y 调试卡片在视口尺寸变化后重新锚定位置。

## 注意事项
- 调用 `attach_scene` 时需确保 `GraphView` 已设置 `overlay_manager`/`mini_map` 属性，以便复用或释放旧实例。
- 与 `app.ui.overlays`、`app.ui.graph.graph_view.overlays` 互相解耦：装配层只负责创建与定位，不直接参与绘制实现。
- 所有方法运行在 UI 线程；若在后台线程触发，请先通过 `QtCore.QMetaObject.invokeMethod` 切回主线程。

