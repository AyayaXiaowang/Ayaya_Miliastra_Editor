# 千星沙箱网页处理工具 目录说明

## 目录用途
- 提供 Web-first 的 UI 预览/检查/导出工具，并以私有扩展 `plugin.py` 的形式集成到主程序：读取项目存档的 `管理配置/UI源码/*.html`，在浏览器侧生成 bundle，再由后端调用 `ugc_file_tools` 写回输出 `.gil/.gia` 或导入到项目存档。
- 目标：浏览器侧负责“可视化与静态校验”，后端保证写回口径一致、可复现、fail-fast。

## 当前状态
- **入口/运行态**
  - `plugin.py`：主程序私有扩展入口（注册按钮、启动本地静态服务、挂载 `/api/ui_converter/*`）。
  - `ui_workbench_backend/`：后端实现（HTTP server + bridge + 导入/导出/占位符校验/变量补齐等）；细节见 `ui_workbench_backend/claude.md`。
  - 前端静态资源真源位于仓库 `assets/ui_workbench/`（包含 `ui_app_ui_preview.html` 与 `src/*`）；插件静态服务运行时指向该目录，确保与 tests/mock server 口径一致。
- **离线/开发辅助**
  - `serve_ui_mockups.py`：仅静态服务（用于本地浏览器预览）。
  - `serve_ui_preview_mock_api.py`：静态服务 + mock `/api/ui_converter/*`（不启动主程序也可预览指定项目的 UI 源码）。
  - `run_ui_workbench_export_job.py`：导出任务子进程入口（隔离重写回/验证，避免阻塞主程序 UI）。
- **文档与产物**
  - `写网页提示词.md`：HTML/CSS 写作约定与注意事项（色板/阴影/状态标注等）。
  - `_artifacts/`：调试截图与分析产物（不参与运行逻辑）。

## 注意事项
- 写回/导出属于高风险操作：始终以 `ugc_file_tools/out/` 作为输出目录，不覆盖原始 `.gil`；写回前先备份。
- fail-fast：不使用 try/except 吞错；结构不符合预期直接抛错，避免生成“看似成功但运行期失败”的存档。
- 扩展控件类型/写回规则时，优先改动 `private_extensions/ugc_file_tools/ui_patchers/web_ui/*`（以及其 `claude.md`），保持“前端导出模型 ↔ 写回口径”一致。
- 本文件仅描述目录用途、当前状态与注意事项，不记录修改历史。

