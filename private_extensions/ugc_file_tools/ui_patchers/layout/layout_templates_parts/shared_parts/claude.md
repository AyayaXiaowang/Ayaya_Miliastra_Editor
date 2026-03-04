## 目录用途
- `layout_templates_parts/shared.py` 的拆分实现区：承载 UI 写回所需的低层共用工具（lossless dump、最小 patch 写回、GUID 分配、children varint stream、layout registry、RectTransform 操作等）。
- 对外稳定入口仍为 `ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared`（薄门面 + re-export）。

## 当前状态
- parts 目录仅用于内部实现拆分；外部模块不应直接依赖 `shared_parts/*` 的具体路径。

- `_write_back_modified_gil_by_reencoding_payload(...)`：默认仍采用“最小 patch”策略（保留原始 wire bytes，仅 patch root field_40/field_9/field_5）。
  - 额外能力：当 `raw_dump_object['4']` 中存在 **baseline 缺失的新增 root 字段** 时，会将这些字段以 protobuf-like wire 形式追加写回（不替换已有字段），用于支持“极空 base .gil bootstrap 补段”（否则新增段会被策略忽略，导致编辑器侧布局行为异常）。

## 注意事项
- 不使用 try/except；结构不一致/字段缺失直接抛错（fail-fast）。
- 需要跨模块复用的能力必须以 **公开 API（无下划线）** 由门面层统一导出，避免外部 `from ... import _private_name`。

