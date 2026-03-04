## 目录用途
- `node_graphs_importer.py` 的拆分实现区：按职责承载“节点图源码扫描/graph_id 分配/GraphModel 导出/写回 .gil”等实现细节，降低单文件复杂度。
- 对外稳定入口仍为 `ugc_file_tools.project_archive_importer.node_graphs_importer`（薄门面 + re-export）。

## 当前状态
- 该目录为实现拆分区（parts），不建议外部代码直接依赖具体子模块路径。
- 子模块按职责拆分（例如：types/specs/context/export/import），由门面层统一汇总导出。
 - GraphModel 导出以 graph_cache 的 result_data 为准，包含 `data.graph_variables`（来自代码级 `GRAPH_VARIABLES` 解析）；写回阶段会以该变量表生成 GraphEntry['6']。
- 节点图写回的“同名覆盖”策略为 **(scope, graph_name)** 精确匹配：当 base `.gil` 已存在同 scope 同名图时，会复用其 `graph_id_int`，并在写回层按 `graph_id_int` 替换旧 graph entry/group，避免 server/client 同名时互相覆盖。
- 节点图写回支持可选“同名节点图冲突策略”（导出中心 selection-json 透传）：`NodeGraphsImportOptions.node_graph_conflict_resolutions` 可按 `graph_code_file` 逐个指定 `overwrite/add/skip`：
  - overwrite：保持默认同名覆盖（复用 base 同名图 id）
  - add：使用 `new_graph_name` 作为写回输出名，从而不命中“同名覆盖”，写入为新图（必要时自动分配新 graph_id_int）
  - skip：跳过该图（不会导出 GraphModel，也不会写回 `.gil`）
- 节点图写回对“单图 strict 解析失败（GraphParseError）”采用 best-effort：跳过该图并记录到 `report.skipped_graphs[]`（包含 reason/error），避免阻断整次写回。
- 当全部节点图被 skip（冲突策略/strict 解析失败等）且输出文件尚不存在时，会先复制 base `.gil` 作为输出，保证导出产物与后续 copy 步骤可用。
- 节点图写回支持可选信号策略：`prefer_signal_specific_type_id` 开启时，满足静态绑定且 base 映射可用的信号节点可将 runtime type_id 切换为 signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx；由 base `.gil` 的 node_def_id 0x4000xxxx/0x4080xxxx 推导），以对齐端口展开/绑定口径。
- 节点图写回支持 `entity_key/component_key` 手动覆盖：当参考 `.gil` 按名称找不到时，可通过 `NodeGraphsImportOptions.id_ref_overrides_json_file` 注入占位符 name→ID 覆盖映射（导出中心缺失行双击选择会自动生成并透传）。

## 注意事项
- 整体以 fail-fast 为主：结构/模板/路径不符合预期直接抛错；但批处理写回允许对单图解析失败做显式 skip 并回报到 report（不静默吞错）。
- 跨模块复用遵循导入策略：对外只暴露门面层的公开 API；内部实现可演进但需保持门面层函数签名稳定。
- 避免在 import 阶段触发重依赖初始化；需要时在函数内部延迟导入（例如 engine 侧模块）。

