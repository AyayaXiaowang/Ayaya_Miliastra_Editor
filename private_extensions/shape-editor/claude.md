## 目录用途
- `shape-editor/`：网页画板工具（私有插件），用于在浏览器中编辑矩形/圆形等形状，并导出为“伯乐识马”等玩法所需的布局数据（JSON / `.gia`）。

## 当前状态
- 前端入口：`index.html` + `shape_editor_entry.js`；交互/图层/持久化/导出等核心逻辑位于 `src/*.js`。
- 后端桥接：`shape_editor_backend/` 提供本地静态服务与 `/api/shape_editor/*`，负责项目存档读写与 `.gia` 导出；细节见 `shape_editor_backend/claude.md`。
- 像素图辅助：`perfectPixel/` 提供像素矩阵生成算法与示例，用于网页侧的像素工作台能力。

## 注意事项
- 插件通过将 `private_extensions/` 注入 `sys.path` 复用同级 `ugc_file_tools`（导出写入器等）；避免在本插件内重复实现 `.gia` 写出逻辑。
- 网页样式复用仓库根 `common.css`；前端第三方依赖以 `index.html` 的脚本引用为准。
- 画布坐标/锚点/旋转与导出约定以 `shape_editor_backend/settings.py` 与 `shape_editor_backend/export_gia.py` 为单一真源，避免前后端口径漂移。
- 本文件不记录修改历史，仅保持“目录用途 / 当前状态 / 注意事项”的实时描述。
