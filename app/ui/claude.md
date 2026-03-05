## 目录用途
- 基于 PyQt6 的应用层 UI：主窗口、节点图画布、资源库浏览、任务清单与执行监控等交互组件。
- UI 只负责呈现与交互；资源读取/索引/持久化通过控制器与 `engine/resources` 完成（资源根：`assets/资源库`）。

## 当前状态
- **主窗口装配**：`main_window/` 以 Mixin + Presenter + 服务层组织模式切换、导航与右侧面板联动（详见 `main_window/claude.md`）。
- **控制器层**：`controllers/` 负责把 UI 交互转换为对资源/运行态的操作（Package/Graph/Navigation/FileWatcher 等）。
- **图编辑器 UI**：`graph/` 提供 `GraphView/GraphScene`、图形项渲染与只读/预览能力；图结构的合法性与排版语义以 `engine` 为权威。
- **任务清单**：`todo/` 负责步骤树/详情/预览/执行入口的 UI 组织；图预览复用同一套画布但受只读能力约束。
- **执行监控**：`execution/` 提供执行驱动与监控面板（日志/截图/叠加），用于“教学式”离线演示与执行过程可视化。
- **基础设施**：`foundation/` 提供主题 token、基础控件与通用 UI 工具方法（对话框/样式/菜单等）。
- **Web-first 界面控件组**：UI 源码预览/转换入口由 `private_extensions/千星沙箱网页处理工具` 提供；主程序 UI 侧仅保留入口与占位说明，避免重复维护两份前端。

## 注意事项
- **依赖方向**：仅允许 `app/ui -> app/models`；严禁 `app/models -> app/ui`。
- **I/O 边界**：不要在 UI 层直接 `open()` 读写资源文件或绕过索引；统一走 `ResourceManager`、`PackageController` 等控制器入口。
- **异常处理**：UI 层不使用 `try/except`；错误直接抛出（或交由显式集中处理入口展示/记录），禁止静默失败。
- **样式统一**：主题与颜色统一使用 `ThemeManager` / token；避免散落硬编码 QSS/颜色字符串。
- **面板与模式**：模式切换与右侧面板操作统一走主窗口服务/控制器；避免在任意 Widget 内直接操作 `QTabWidget/QStackedWidget` 造成上下文漂移。
