## 目录用途
`app/ui/graph/library_pages/`：各类“资源库/列表类页面”的 PyQt6 实现（节点图库、元件库、实体摆放、战斗预设、管理配置库、项目存档页等）。页面复用 `DualPaneLibraryScaffold` 与通用 Mixin，并与主窗口右侧详情面板联动。

## 当前状态
- **统一页面协议**：库页实现 `LibraryPageMixin`（`set_context/reload/get_selection/set_selection`），通过 `notify_selection_state(...)` 让主窗口集中控制右侧容器显隐与联动。
- **视图模型**：上下文仅区分 `PackageView`（具体项目存档）与 `GlobalResourceView`（共享视图）；PackageView 下会混入共享资源并以“共享徽章”标识。
- **异步与预览**：项目存档页的预览不自动切包，资源列表来自磁盘扫描（`ResourcePreviewScanService`）；双击节点图等重任务通过 `GraphResourceAsyncLoader` 后台加载，避免阻塞 UI。
- **写操作语义**：复制/派生会生成新的业务 ID；删除在 PackageView 表示“从当前包移出/归档”，在 GlobalResourceView 才是物理删除（会做二次确认与引用提示）。
- **扩展点**：节点图库/项目存档页提供工具栏扩展入口（`ensure_extension_toolbar_*`），便于私有扩展注入按钮或状态控件而不改内部布局。

## 注意事项
- 页面以“展示 + 发出操作请求”为主；涉及索引/移动/删除必须走 `ResourceManager`/`PackageIndexManager`/控制器，不要在页面内散落写盘逻辑。
- 左右分栏默认使用 `QSplitter`：不要固定宽度；刷新/重建后不要继续持有旧 Qt Item。
- 主题与交互一致性：颜色/字体/对话框优先复用 `ThemeManager` 与基础设施工具；不使用 try/except 吞错。
- 调试输出需可控：避免在正常交互路径无条件 `print()` 刷屏；需要时统一走 `engine.utils.logging.logger` 并由 settings 的 verbose 开关控制。