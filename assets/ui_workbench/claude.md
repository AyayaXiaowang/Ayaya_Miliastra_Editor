## 目录用途
- 存放 **UI Workbench 的前端静态资源真源**（HTML + ES Modules）：UI源码预览、扁平化、检查器、导出控件列表等 Web-first 工具链。
- 该目录作为“单一真源”被以下入口复用：
  - 主程序私有扩展 `private_extensions/千星沙箱网页处理工具`（后端提供 `/api/ui_converter/*`，静态前端从此目录提供）
  - `tests/` 的 UI Web 回归（通过临时静态服务器直接服务此目录）
  - 离线预览脚本（mock /api + 静态服务）

## 当前状态
- `ui_app_ui_preview.html`：唯一入口（预览/检查/导出）。
- `ui_html_workbench.html`：内部/自动化入口（用于测试与回归；运行时插件会跳转到 `ui_app_ui_preview.html`）。
- `src/`：前端模块实现（预览、扁平化、导出模型、校验、自动化等）。

## 注意事项
- **不要在私有扩展目录维护第二份前端**：插件只保留后端能力与入口脚本，静态前端以本目录为准，避免样式/层级/契约漂移。
- **ID 约束**：前端通过 `getElementById` 强绑定关键 DOM（例如 `src/dom_refs.js`）；改动 HTML 结构时必须保留既有 ID。


