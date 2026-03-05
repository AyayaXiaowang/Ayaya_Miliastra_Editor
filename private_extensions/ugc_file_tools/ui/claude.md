## 目录用途
- UI（`.gil`）相关的可读 dump/提取工具：从 dump-json（numeric_message）中抽取 UI record 列表、GUID/名称/RectTransform 等信息，供导入/写回/验证与诊断脚本复用。

## 当前状态
- `readable_dump.py` 提供公开提取 API（例如 `extract_ui_record_list` / `extract_primary_guid`），并兼容写回链路的 lossless dump 形态：
  - 当 `root4/9` 为 `<binary_data>` 时会解码回 dict（numeric_message）。
  - 当 `4/9/502(UI record list)` 内条目为 `<binary_data>` 时，会解码为 dict，确保后续 GUID 收集/查找/唯一性校验不遗漏。
  - 兼容旧/异常样本：当 UI record 的 `component_list(505)` 内出现 `"<binary_data> "`（空 bytes）条目时，会将其归一化为 `{}`，避免后续导出/解析因列表内混入 `str` 发生类型分叉。

## 注意事项
- 不使用 try/except 吞错；结构不符合预期应直接抛错（fail-fast），便于定位 dump/写回口径问题。
- UI record 的 GUID 提取以 `record['501']` 为主（兼容 list/int 两种形态）；调用方不应假设 record 一定是 dict（请优先使用本模块的提取函数）。

