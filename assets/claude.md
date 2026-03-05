## 目录用途
只读资源目录：包含资源库、OCR 模板与少量静态前端占位资源，与 `app/runtime/` 的可写运行态区分离。

## 当前状态
- `资源库/`：UGC 资源总库（共享/项目存档资源）
- `ocr_templates/`：OCR 模板图片与 profile 目录
- `ui_workbench/`：只读占位资源（完整 Web 工具由私有扩展提供）

## 注意事项
- 本目录视为只读：运行期产物与缓存统一写入 `settings.RUNTIME_CACHE_ROOT`（默认 `app/runtime/cache/`）。
- 资源读写/索引统一通过 `engine.resources`，避免上层工具裸 `open()` 直接改资源文件。
- 读取文本资源时统一使用 UTF-8（必要时兼容 BOM）。

