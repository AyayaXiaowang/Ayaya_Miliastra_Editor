# shape_editor_backend 目录说明

## 目录用途
- 为 `private_extensions/shape-editor` 提供“主程序插件化接入”的后端桥接层：启动本地静态服务并暴露 `/api/shape_editor/*`。
- 负责项目存档读写（实体摆放/画布/状态/素材），并将网页画布内容导出为 `.gia`（实体或元件）。

## 当前状态
- `bridge.py`：对外桥接类（生命周期、主窗口注入、打开浏览器、导出入口）。
- `http_server.py`：本地静态服务与 API handler（静态资源 + JSON API）。
  - 端口：默认 `17890`，可用环境变量 `AYAYA_LOCAL_HTTP_PORT` 覆盖；占用时会顺延扫描一段端口范围。
  - 静态站点根目录为 `workspace_root`；前端资源位于 `private_extensions/shape-editor/`（含 `common.css`）。
- `export_gia.py`：画布 payload → decorations_report → 生成 `.gia`（复用 `ugc_file_tools.gia.*` 的写出器）。
- `settings.py`：导出配置单一真源（base `.gia` 路径、像素→世界坐标换算、颜色/形状→template_id 映射、pivot/anchor/轴向等口径）。
- `pixel_art.py`：像素图处理服务：对接仓库内 `perfectPixel` 算法，支持可选 palette 预量化以消除碎色。
- `project_persistence.py`：项目级持久化（实体列表、新建/另存/复制/重命名/删除、参考图与像素素材落盘、最近打开状态恢复等）。

## 注意事项
- 插件会在 QApplication 创建前被 import：不要在模块顶层导入 PyQt6；Qt 相关逻辑必须延迟到主窗口 hook 内执行。
- fail-fast：不吞错；导出失败应直接抛出并返回明确错误信息，避免生成不可用产物。
- 参考图不参与导出：后端导出会忽略 `isReference=true` 的对象；参考图仅用于编辑期对齐与取色。
- 坐标/锚点/旋转与导出约定以 `settings.py` 与 `export_gia.py` 为单一真源，避免前后端口径漂移。
- 目录名 `private_extensions/` 为历史约定保留；本工具随仓库分发并非“私有不可用”。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

