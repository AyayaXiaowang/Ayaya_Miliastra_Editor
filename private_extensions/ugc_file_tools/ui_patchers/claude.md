# ui_patchers 目录说明

## 目录用途
- 存放“UI 写回/补丁”工具：以 `.gil` 二进制为目标，对可定位的字段/片段做**最小化改动**并输出新的 `.gil`。
- 与 `ui_parsers/` 分离：`ui_parsers/` 负责“读”；`ui_patchers/` 负责“写回/改动”。

## 当前状态
- 代码按子域拆分（每个子目录均有更详细的 `claude.md`）：
  - `misc/`：小型写回脚本（进度条改色、控件 variants、文本框等）。
  - `layout/`：布局与控件组库的写回（布局注册表、布局 root/children、模板沉淀/放置、画布锚点修复、布局资产 `.gia` 导出）。
  - `schema/`：基于 `ui_schema_library` 的 schema 克隆与变量默认值/规格相关工具。
  - `web_ui/`：Web Workbench 导出的 bundle/inline-widgets → `.gil` 写回（含 GUID 复用、组件打组、变量补齐与写回后校验）。
- 主要入口（稳定导入路径）：
  - Web 导入：`web_ui/web_ui_import.py`
  - 布局/模板：`layout/layout_templates.py`
  - Schema 克隆：`schema/schema_clone.py`

## 注意事项
- 产物与报告统一写入 `ugc_file_tools/out/`，不覆盖原始样本；写回前务必备份 base `.gil`。
- fail-fast：不使用 try/except 吞错；遇到结构不一致直接抛错，避免写坏存档。
- 跨模块复用走公开 API（无下划线）；目录拆分后不要再从旧路径导入（例如把 `misc/*.py` 当作顶层模块导入）。
- 本文件仅描述目录用途、当前状态与注意事项，不记录修改历史。

