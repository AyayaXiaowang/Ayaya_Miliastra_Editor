# ugc_file_tools/commands/diagnostics 目录说明

## 目录用途

- 收口 **只读诊断/查询/清单导出/合约校验/状态刷新** 类命令入口（例如 `inspect_*` / `list_*` / `check_*` / `refresh_*`）。

## 当前状态

- 大多数工具只读；如有写盘行为，必须把输出统一写入 `ugc_file_tools/out/`（或明确的运行时缓存目录），避免污染项目存档目录。
- 合约校验类工具用于保护写回链路：发现违例应直接抛错并给出报告路径。
- 目前包含：
  - `inspect_json`（通用 JSON 深层路径探测；实现位于本目录）
  - `inspect_ui_guid` / `inspect_parsed_node_graphs`
  - `list_gil_ids` / `list_gia_entities`
  - `check_graph_variable_writeback_contract`
  - `check_get_custom_variable_dict_outparam`（端到端校验：Get_Custom_Variable 的字典 OUT_PARAM(MapBase K/V) + `S<T:D<K,V>>` 的 concrete/runtime_id + `indexOfConcrete` 是否对齐 GraphModel 推断；支持 `--inspect-gil` 直接校验现成导出产物，避免“字典退化为整数”）
  - `refresh_project_archive_parse_status`

## 注意事项

- 不使用 `try/except`；错误直接抛出（fail-fast）。
- 复用既有“单一真源”模块（例如 UI GUID 解析统一走 `ui/guid_resolution.py`），避免口径分叉。
