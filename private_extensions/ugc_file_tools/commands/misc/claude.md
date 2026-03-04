# ugc_file_tools/commands/misc 目录说明

## 目录用途
- 存放 `ugc_file_tools` 的 **杂项/内部工具入口**（通常是诊断、一次性迁移、对照检查、或保留旧命令名的兼容 CLI）。
- 这些脚本应保持“入口薄、逻辑下沉”：可复用实现放到 `ugc_file_tools/*` 具体子域（例如 `node_graph_writeback/`、`gil_dump_codec/`、`ui/guid_resolution.py`），本目录仅做参数解析与调用编排。

## 当前状态
- 本目录包含若干 legacy/辅助入口（例如 `inspect_json`、`inspect_ui_guid`、`sync_*_registry_from_gil`、以及节点图写回/补丁类工具）。
- `graph_model_json_to_gil_node_graph.py`：GraphModel(JSON) → `.gil` 节点图段写回的 CLI 薄入口（内部诊断/二分/最小自举用途）；核心实现位于 `ugc_file_tools/node_graph_writeback/`，支持模板克隆模式与 `--pure-json` 模式。
  - 导出中心/交付进游戏测：推荐使用 `ugc_file_tools project import`（导出中心同款 pipeline），避免在“节点图列表/索引”等 UI 依赖字段上与真源口径分叉。
- `sync_graph_code_to_gil_preserve_graph_variables.py`：当节点图源码不包含 `ui_key:` 占位符时，不要求选择 UI 导出记录/快照；仅在确实需要回填 ui_key 时才会从记录中挑选 `ui_guid_registry_snapshot`。
- `write_graph_generater_package_test2_graphs_to_gil.py`：内部批量写回脚手架；`--base-gil` 默认使用“带基础设施的空存档”样本（`ugc_file_tools/builtin_resources/empty_base_samples/empty_base_with_infra.gil`），避免真空基底导致后续段缺失需额外 bootstrap。
- `export_gil_writeback_variants_for_bisect.py`：批量导出多份“节点图写回 GIL 变体”，用于进游戏二分定位“到底哪一处写回补丁让真源可识别”：
  - 通过环境变量 `UGC_WB_DISABLE="flag1,flag2"` 禁用指定补丁点（默认全开）。
  - 默认生成 2 份：`A_all_enabled` 与 `B_disable_all_patches`（禁用所有已接入开关的补丁点）。
  - 产物落盘到 `ugc_file_tools/out/`，可选 `--copy-to <dir>` 额外复制到用户目录便于直接进游戏测试。
- `auto_wire_graph_writeback_gaps_in_gil.py`：从示例 GraphModel 读取端口类型证据时兼容 `input_port_types/effective_input_types`（支持仅携带快照字段的 JSON 形态）。
- `patch_gil_add_motioner.py`：危险写盘：为指定实例补齐“运动器(Motioner)”组项（实例段 `root4/5/1[*].7` 追加 `{1:4,2:1,14:{505:1}}`），输出新 `.gil` 到 `ugc_file_tools/out/`；默认使用 lossless 解码（`prefer_raw_hex_for_utf8=True`）以避免无关字段漂移。
- `export_ui_workbench_bundles_from_html.py`：项目存档 `UI源码/*.html` → 生成/更新 `UI源码/__workbench_out__/*.ui_bundle.json`（用于导出中心导出前自动更新 UI bundle；需要 Playwright/Chromium；stderr 输出可解析进度）。

## 注意事项
- 不使用 `try/except`；错误直接抛出（fail-fast）。
- 避免在脚本内复制 GraphModel 结构适配/遍历逻辑：统一复用 `ugc_file_tools/graph/model_ir.py` 等公共入口。
- 若新增工具可长期维护且对外稳定，优先迁移到 `ugc_file_tools/commands/` 顶层并在 `tool_registry.py` 注册；本目录更多用于内部脚手架与兼容入口。

