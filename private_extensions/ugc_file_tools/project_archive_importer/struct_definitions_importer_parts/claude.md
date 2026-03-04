## 目录用途
- `struct_definitions_importer.py` 的拆分实现区：承载“结构体 decoded-json/代码级结构体(.py) → 写回 .gil”的实现细节，避免单文件过长。
- 对外稳定入口仍为 `ugc_file_tools.project_archive_importer.struct_definitions_importer`（薄门面 + re-export）。

## 当前状态
- parts 目录仅用于内部实现拆分；门面层统一对外导出 `resolve_project_archive_path / iter_struct_decoded_files / collect_basic_struct_py_files_in_scope / import_struct_definitions_from_project_archive_to_gil` 等稳定入口。

## 注意事项
- 不使用 try/except；发现结构不一致/模板缺失直接抛错（fail-fast）。
- 若需要跨模块复用，优先增加“公开 API（无下划线）”并在门面层 re-export，避免外部依赖 parts 子模块路径。

