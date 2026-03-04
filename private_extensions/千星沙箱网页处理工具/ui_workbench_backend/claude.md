## 目录用途
- 本目录为“千星沙箱网页处理工具”的 Python 后端实现拆分包，用于承载 `plugin.py` 中原本超长的桥接逻辑（HTTP API、占位符校验、导入/导出 `.gil/.gia`、UI 注入等）。
- 该目录是**独立包名**（`ui_workbench_backend`），避免与私有扩展加载器把 `plugin.py` 作为模块 `private_extensions.<插件名>` 执行时产生包名冲突。

## 当前状态
- `bridge.py`：对外聚合类 `_UiWorkbenchBridge`（保持与旧 `plugin.py` 一致的类名与行为）。
- `bridge_base.py`：桥接基础设施（生命周期、打开浏览器、状态 payload、当前包上下文获取、通用字段/调色板常量）。
  - `/api/ui_converter/status` 额外返回 `workbench_static_dir/workbench_backend_dir` 与 `debug_static_probe`（关键静态资源路径/大小/sha256_12），用于排障确认“当前进程实际在用哪一份静态目录/是否吃到最新前端代码”。
  - `/api/ui_converter/status` 同时返回 `suggested_base_gil_path / suggested_gil_paths`：用于 Web 预览页“一键使用当前 .gil 作为基底”（优先从 BeyondLocal 推导“当前沙箱存档 .gil”，并保留 ugc_file_tools 导出设置作为兜底）。
  - `suggested_gil_paths.base_gil_for_signal_defs_path` 兼容字段演进：读取 `UGCFileToolsExportSettings` 时对可选字段使用 `getattr`（如 `base_gil_path/base_gil_for_signal_defs_path`），避免离线预览 `/status` 因缺字段崩溃。
- `bridge_catalog_ui.py`：UI 布局/模板清单与 UI 源码读取/写回相关 API。
- `bridge_placeholder_validation.py`：UI 文本占位符 `{{...}}` 扫描与校验（lv/ps 作用域与字段路径规则）。
  - 方案 S：不再支持 `autofix_missing_lv_variables` 的写盘补齐；缺失变量/字段路径将直接失败并给出“注册表补齐”指引。
- `bridge_import_variable_defaults.py`：将前端给出的 `variable_defaults` 写回当前项目的 `自定义变量注册表.py`（lv/ps 作用域）：
  - `lv.*` 更新 owner="level" 的声明 default_value
  - `ps.*` 更新 owner="player" 的声明 default_value
  - 不再生成 `UI_*_网页默认值.py`；HTML 也不再以 `data-ui-variable-defaults` 作为真源。
- `bridge_export.py`：导出 `.gil/.gia`（含进度条颜色调色板归一化、bundle→inline widgets 转换、token 下载映射）。
  - 方案 S：导出前仅执行 `validate-ui` 等价校验；若 UI 占位符引用闭包不成立则直接失败，要求在注册表补齐变量声明/默认结构。
  - 支持导出 `.gil` 时按需将“按钮组件组”同步保存为【自定义模板】（默认关闭；由前端/调用方显式传参启用）。
  - **HTML 显式模板沉淀**：作者可在 HTML 组件根元素标注 `data-ui-save-template`，导出 `.gil` 时会将该组件组保存为“控件组库自定义模板”；若基底 `.gil` 已存在同名模板则复用并跳过创建。
  - 支持**批量导出**：当调用方传入多个 bundle 时，会依次写回多个布局到同一份输出 `.gil`（用于预览页多选导出）。
  - 批量导出写回 `.gil` 时会固定使用“最初基底存档”推断出的 `base_layout_guid` 作为克隆来源，避免递推过程中推断结果漂移导致后续页面克隆/串页/混乱。
  - 导出 `.gil` 完成后会写入“UI 导出记录”（运行时缓存，包含 `ui_guid_registry` 快照与输出 `.gil` 路径），供后续节点图 `.gia` 导出选择“回填记录”避免回填错 GUID。
  - 对外仓库约束：导出链路不依赖 `ugc_file_tools/save/**`（该目录默认忽略不对外）；需要 seed/模板时仅使用 `ugc_file_tools/builtin_resources/**` 下可公开的内置资源（缺失直接 fail-fast）。
- `bridge_import_layouts.py`：导入布局（template/bundle）到管理配置（含按钮打组策略与 ID/名称重写）。
- `bridge_import_ui_pages.py`：导入“网页 → bundle”到当前项目存档，并同步维护 `management.ui_pages`（复用 `apply_ui_html_bundle_to_current_package`）。
- `bridge_internal.py`：内部 glue（启动本地静态服务、生成预览 URL、UI 按钮注入、通用 ID/名称工具函数）。
  - 左侧导航入口注入优先使用 `NavigationBar.ensure_extension_button(...)`（若主程序提供），否则回退为旧版 `layout.insertWidget(...)` 直插按钮，保持兼容。
  - 导航按钮对外命名统一为“UI预览”（内部 key 仍为 `ui_converter`，避免破坏既有扩展点与测试契约）。
- `http_server.py`：本地静态服务器与 `/api/ui_converter/*` 请求处理器（包含 Cache-Control/MIME 强制规则）。
  - `/api/ui_converter/*` 会输出简洁访问日志（静态资源默认不刷屏），用于排障确认“请求是否真正打到后端”。
  - `export_gil/export_gia` 等重任务会启动独立 Python 子进程执行（入口脚本位于插件根目录 `run_ui_workbench_export_job.py`），将可能持有 GIL/DLL 的写回/验证/打包完全隔离出主进程，避免导出期间 PyQt UI 卡死。
  - `StaticRequestHandler`：静态服务基础能力（唯一实现）：ESModule MIME 强制 + 开发期 no-store；运行时的 `_WorkbenchRequestHandler`（含 `/api/ui_converter/*`）与离线脚本都会复用它，避免多份实现漂移。
  - **静态目录单一真源**：运行时静态前端默认从 `assets/ui_workbench/` 提供；导出子进程入口脚本仍从插件目录解析（后端真源），避免“静态目录切换后找不到 run_ui_workbench_export_job.py”。
  - 端口策略：默认固定 `17890`，可用环境变量 `AYAYA_LOCAL_HTTP_PORT` 覆盖；若端口已被占用则向上顺延扫描一段，扫描失败才回退为系统临时端口。
  - 提供 `GET/POST /api/ui_converter/base_gil_cache`：用于缓存“预览页选择的基底 `.gil`”（二进制落盘），以便在插件静态服务端口变化时仍可稳定恢复基底文件（不依赖浏览器 origin）。
  - **统一入口策略（运行时）**：在插件静态服务中将 `/` 与 `/ui_html_workbench.html` 强制跳转到 `/ui_app_ui_preview.html`，避免用户误入 Workbench 页面。

## 注意事项
- **不要在模块顶层导入 PyQt6**：UI 注入相关逻辑必须延迟导入，避免私有扩展在 QApplication 创建前被 import 时破坏启动顺序。
- **不要吞错**：保持“失败直接抛出”的原则，便于排障与回归测试定位。
- **mixin 聚合约束**：`_UiWorkbenchBridge` 通过多继承组合多个 mixin；`bridge_base.py` 不应定义 `_ensure_server_running/_inject_*` 等同名 stub，否则会因 MRO 优先命中 Base 而导致运行期异常。
- **对外兼容性**：`plugin.py` 仍需暴露 `_UiWorkbenchBridge`、`install(workspace_root)` 与全局 `_BRIDGE`，以兼容主程序的 `sys.modules["private_extensions.千星沙箱网页处理工具"]` 访问方式与现有测试用例。
