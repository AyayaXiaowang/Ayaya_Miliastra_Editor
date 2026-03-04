## 目录用途
引擎核心层（纯逻辑）：图模型与解析、节点系统、布局、校验、资源视图与通用工具等；对上层提供稳定公共 API。禁止反向依赖应用层与插件层。

## 当前状态
- 稳定入口统一由 `engine/__init__.py` 导出；上层（`app/plugins/tests`）应只从 `engine` 顶层导入。
- 活跃子模块包括：`graph/`、`nodes/`、`layout/`、`validate/`、`resources/`、`configs/`、`utils/`。
- 引擎层只负责“建模/解析/校验/排版/只读视图”；运行时代码生成与执行编排位于应用层或工具层。

## 注意事项
- 仅存放无 UI/无外设 I/O 的纯逻辑代码；不使用 `try/except` 吞错。
- 严禁循环依赖与跨层反向依赖：禁止依赖 `app/*`、`plugins/*`、`assets/*`、`core/*`（以及任何未纳入仓库的本地脚本/工具链）。
- 资源库根目录为 `assets/资源库`（由 `engine.resources.ResourceManager` 管理与扫描），引擎层不要硬编码其他资源路径；运行期缓存统一落在 `settings.RUNTIME_CACHE_ROOT`（默认 `app/runtime/cache`）。

