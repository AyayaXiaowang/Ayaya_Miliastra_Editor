## 目录用途
`app/ui/graph/library_pages/package_library/` 是“项目存档页（Packages view）”的实现子模块，用于拆分 `PackageLibraryWidget` 的 UI 装配、预览树构建、懒加载、资源显示名缓存与存档操作等职责，避免单文件持续膨胀。

## 当前状态
- **对外入口保持稳定**：外部仍应从 `app.ui.graph.library_pages.package_library_widget` 导入 `PackageLibraryWidget`；该文件作为薄门面，具体实现位于本目录。
- **职责拆分**：按 mixin 分离左侧列表/工具栏、右侧预览树、懒加载“加载更多”、资源显示名缓存与存档操作等动作处理；懒加载分页的目标索引计算复用 `app.common.pagination.compute_lazy_pagination_target_index(...)`（纯算法层可测），UI 侧仅负责树节点装配与信号连接。
- **预览语义**：预览资源列表来自磁盘扫描（由 `app.runtime.services.resource_preview_scan_service.ResourcePreviewScanService` 提供），避免受 `ResourceManager` 当前作用域影响；其中结构体定义在预览中按 `basic/ingame_save` 分类展示同样基于扫描结果（目录即分类 + `STRUCT_TYPE/STRUCT_PAYLOAD` 回退），不依赖 `ResourceManager.load_resource()`。
- **存档重命名入口**：目录模式下项目显示名以项目目录名（package_id）为真源；目录级重命名影响导入路径与引用，当前 UI 暂不提供“重命名项目存档”入口（按钮禁用）。

## 注意事项
- 本目录代码属于 UI 层（PyQt6）；纯逻辑/可测试的扫描与缓存策略应尽量下沉到 `app/runtime/services/`。
- 不在此处直接写盘资源内容；存档目录级操作通过 `PackageIndexManager` 统一执行。

