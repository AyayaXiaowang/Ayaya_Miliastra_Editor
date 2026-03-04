# ugc_file_tools 目录说明

## 目录用途
- Graph_Generater 的 UGC 资产工具链（`.gil/.gia`）：解析/导出/对照诊断/批量写回，并作为真源（官方编辑器/真实存档）与离线沙箱（项目存档/Graph Code）的桥接层。
- 设计原则：模块化拆分 + 薄入口（`commands/`）+ 共享编排（`pipelines/`），fail-fast（不吞异常）。

## 当前状态
- **入口**
  - 单工具：`commands/`（由 `tool_registry.py` 注册；`private_extensions/run_ugc_file_tools.py tool <name>` 转发）
  - 统一 CLI：`ugc_unified.py`（实现拆分在 `unified_cli/`）
  - UI 集成：`ui_integration/`（“导入/导出中心”编排，避免多入口口径漂移）
- **核心域**
  - `.gil`：`gil/`、`gil_dump_codec/`、`gil_package_exporter/`、`gil_signal_repair/`
  - `.gia`：`gia/`、`gia_export/`（VarBase 语义：`gia/varbase_semantics.py`；二维码实体 `.gia`：`gia_export/qrcode_entity/`）
  - 节点图：`graph/`、`graph_codegen/`、`node_graph_semantics/`、`node_graph_writeback/`
  - UI：`ui_parsers/`、`ui_patchers/`、`ui_schema_library/`
  - 项目存档维护：`preview_merge/`（选关预览展示元件/实例的 keep_world 合并；生成新模板/实例并可补丁 GraphVariables）。
  - UI Workbench（HTML→bundle）：通过 `tool export_ui_workbench_bundles_from_html` 生成/更新项目存档 `UI源码/__workbench_out__/*.ui_bundle.json`，供 UI 写回链路消费（依赖 Playwright/Chromium）。
  - 历史工具集：旧 `UGC-File-Generate-Utils/` 已移除；二维码实体导出不再依赖路径注入。
  - 契约层：`contracts/`（跨域 single source of truth）
- **常用诊断工具（只读/报告）**
  - `check_get_custom_variable_dict_outparam`：检查字典 OUT_PARAM 的 K/V concrete 是否对齐 GraphModel 推断
  - `report_gil_payload_graph_ir_diff`：对比两份 `.gil` 的 payload Graph IR 差异
  - `report_gil_dump_json_diff`：对比两份 `.gil` 的 dump-json（数值键 JSON）差异，并按路径列出变更点
  - `report_gil_payload_root_wire_sections_diff`：更硬的 wire-level 段对照（按 payload_root field_number 对比 length-delimited payload bytes 是否完全一致，用于证明是否发生 payload drift）
  - `inspect_gil_signals`：提取 `.gil` 的 signal entries 与节点图信号节点摘要
- `export_center_scan_base_gil_conflicts` / `export_center_scan_gil_id_ref_candidates` / `export_center_identify_gil_backfill_comparison`：导出中心 UI 专用子进程 helper（冲突扫描/缺失 ID 候选/回填识别）。
  - 回填识别会对 base/id_ref `.gil` 的“可复用分析结果”做运行期缓存（`app/runtime/cache/ugc_file_tools/export_center/backfill_gil_analysis/`），重复识别优先复用缓存以避免再次 decode `.gil`。
- **常用补丁工具（危险写盘）**
  - `patch_gil_add_motioner`：为指定实体实例补齐“运动器(Motioner)”组项（实例段 `root4/5/1[*].7` 追加 `{1:4,2:1,14:{505:1}}`），输出新 `.gil` 到 `out/`。
- **目录策略**
  - `out/`：中间产物与报告（可删可重建，路径由 `output_paths.py` 收口）
  - `builtin_resources/`：程序内置资源（运行必需/默认依赖的 seed；对外仓库可版本化）
    - 默认 dtype：`builtin_resources/dtype/dtype.json`
  - `save/`：人工维护的输入样本（可为空；可能含未授权真源样本，默认不对外）
  - `parse_status/`：解析状态输出（按包聚合）

## 注意事项
- 输出路径：写回工具的 `output_*` 默认只接受 basename，并统一写入 `out/`，避免路径漂移与重复嵌套。
- `.gia` 导出目录：生成/写回的 `.gia` 会复制到 BeyondLocal `Beyond_Local_Export`（同时 `out/` 保留可追溯产物）。
- fail-fast：不使用 try/except；结构/模板不符合预期直接抛错。
- Windows 用户目录相关路径通过 `Path.home()` 推导，不在源码中写死盘符/用户名。
- 占位符参考映射：`id_ref_from_gil.build_id_ref_mappings_from_payload_root(...)` 支持从已解码的 payload_root 构建映射，供上层复用并避免重复解码；并会对名字字段的 `<binary_data> 0A ..`（嵌套 message bytes）做解包，输出可读名称供回填识别/候选列表匹配。
- `.gia` VarBase 语义提取：优先复用 `gia/varbase_semantics.py`；泛型/反射端口常见 `ConcreteBase(10000)` 包裹需先解包再读 inner。
- `gil_dump_codec/protobuf_like.py` 会优先判定 utf8 文本；遇到 `{raw_hex, utf8}` 形态时按需从 `raw_hex` 反解嵌套 message，避免字符串/字典默认值被误判为空。
- `.gil` 装饰物（模板 `metadata.common_inspector.model.decorations`）写回不走实体摆放段：当前落盘到 `payload_root['27']`（root27，定义+挂载两表结构），由 `project_archive_importer/templates_importer.py` 负责。
- 导入路径约定：允许以 `private_extensions.ugc_file_tools.*` 方式导入，本包会自动 alias 为顶层 `ugc_file_tools`，以兼容内部绝对导入。