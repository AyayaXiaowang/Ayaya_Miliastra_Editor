# gil_package_exporter 目录说明

## 目录用途
- 承载 `extract_gil_to_package.py` 的核心实现：将 `.gil` 尽可能解析并导出为 Graph_Generater 可识别的“项目存档”目录结构（模板/实体/管理配置/节点图原始解析等）。
- 解析状态文档统一输出到 `ugc_file_tools/parse_status/`，避免写入 Graph_Generater 资源库与主工程目录。

## 当前状态
- 主要入口：`runner.export_gil_to_package(...)`（由 `ugc_file_tools/commands/extract_gil_to_package.py` 薄 wrapper 转发）。
  - 支持选择性导出：`selected_node_graph_id_ints` + `export_*` 资源段开关（用于 UI“先分析→勾选→导入”）。
- `node_graph_listing.py`：`list_gil_node_graphs(...)` 读取 `.gil` 并列出节点图清单（不落盘）。
- 导出模块按职责拆分：解码/扫描/资源导出/报告/占位符生成（templates/instances/structs/signals/section15/ui_widget_templates/node_graph_raw 等）。
  - 必要时会生成占位模板/占位节点图，保证引用闭包可被资源索引与校验。
- UI 相关（可选）：在导出 UI 控件模板/记录时，会将结构签名与代表性模板沉淀到 `ugc_file_tools/ui_schema_library/data/`，用于后续“按 schema 克隆 record”式写回。
- 默认 `dtype.json`：`ugc_file_tools/builtin_resources/dtype/dtype.json`（由 `paths.resolve_default_dtype_path()` 收口）。

## 注意事项
- 避免在 import 阶段做重依赖初始化；可选能力应在启用开关后再导入，确保 `--help` 可用。
- fail-fast：不使用 `try/except`；解析错误直接抛出，便于定位与保证一致性。
- 输出目录应为 `assets/资源库/项目存档/<package_id>`；历史“存档包目录”已废弃，不再作为输出目标。
- 本文件仅描述“目录用途/当前状态/注意事项”，不写修改历史。

