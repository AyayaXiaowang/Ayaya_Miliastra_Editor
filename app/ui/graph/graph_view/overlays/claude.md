## 目录用途
`app/ui/graph/graph_view/overlays/`：`GraphView` 级叠层组件。在 view/viewport 坐标系渲染辅助 UI（小地图、标尺、搜索、性能与加载遮罩、平移/缩放冻结），不直接修改 `GraphScene` 或 `GraphModel`。

## 当前状态
- **小地图**：`minimap_widget.py` 的 `MiniMapWidget` 缓存场景边界与缩略图，并对超大图降级为模型级渲染；支持点击/拖拽跳转视口。
- **标尺/缩放指示**：`ruler_overlay_painter.py` 的 `RulerOverlayPainter` 在 `GraphView.paintEvent` 叠加坐标刻度，并显示当前缩放百分比。
- **画布搜索**：`graph_search_overlay.py` 的 `GraphSearchOverlay` 提供 Ctrl+F 搜索、高亮与结果导航；输入与结果渲染做防抖/分页，避免大图卡顿。
- **性能/加载/冻结**：`graph_perf_overlay.py` + 监视器用于采样展示；`graph_loading_overlay.py` 统一长任务遮罩；`pan_freeze_overlay.py` / `zoom_freeze_overlay.py` 在交互期间以快照替代真实渲染提升流畅度。

## 注意事项
- overlays 只做渲染与轻量交互；需要改模型必须走控制器/场景命令。
- 缓存重建必须受控（防抖、按需、限幅），避免 `scene.changed` 高频触发下做全图重渲染。
- 覆盖层的层级/父子关系以 view/viewport 语义为准，确保 `raise_()` 与 `NoViewportUpdate` 下行为一致。
