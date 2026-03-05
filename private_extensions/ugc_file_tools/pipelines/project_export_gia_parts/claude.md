# ugc_file_tools/pipelines/project_export_gia_parts 目录说明

## 目录用途
- `project_export_gia` 的实现拆分区：承载“项目存档 → 导出节点图 `.gia`”的业务编排与子步骤实现。
- 目标：降低单文件复杂度，同时保持对外稳定入口仍为 `ugc_file_tools.pipelines.project_export_gia`。

## 当前状态
- `pipeline.py`：主流程（解析 GraphModel → 汇总信号规格 → 导出每张图 `.gia` → 可选 pack/注入/复制）。
  - 导出每张图前会通过 `ugc_file_tools.graph.port_types.standardize_graph_model_payload_inplace(...)` 统一补齐 `graph_variables/edge.id/*_port_types/*_declared_types`，并生成端口类型缺口报告：`out/<out_dir>/reports/port_type_gaps/*.json`。
  - 若缺口报告 `counts.total>0`（存在任意非流程端口 effective 仍为泛型家族），将 fail-fast 抛错阻断导出，禁止静默回退写坏存档。
  - 节点图 specs 来源：当未显式传 `--graph-code` 时，会复用 `project_archive_importer.node_graphs_importer.build_graph_specs(...)` 的扫描结果，并在 pipeline 内归一化为本域 `_GraphExportSpec`（避免跨域 dataclass 导致 `isinstance` 误判）。
- `signals_collect.py`：从 GraphModel payload（含复合节点子图递归）收集“本图用到的信号规格”，用于自包含信号 node_def bundle。
- `graph_specs.py` / `id_ref_placeholders.py` / `ui_placeholders.py`：图选择、占位符回填（entity/component/ui_key；支持手动 `id_ref_overrides`）相关辅助。
  - UIKey 占位符（`ui_key:` / `ui:`）回填默认严格，但对 `UI_STATE_GROUP__*__*__group` 缺失会自动放行并回填为 0（常见原因：Workbench 未导出可写回组容器）。
- `layout_index.py`：布局索引（layout root GUID）自动回填的工程化步骤。
- `pack.py` / `bundle_sidecars.py` / `signal_bundle.py`：多图打包与 bundle 附带产物。
- `types.py`：Plan/回调等类型定义。

## 注意事项
- pipeline 只接收**显式参数**，不负责 argparse/UI 交互；错误直接抛出（fail-fast）。
- 跨模块复用必须走**公开 API（无下划线）**，禁止 `from ... import _private_name` 的越层私有依赖。
- 节点类型映射（`node_type_semantic_map.json` → `node_def_key(canonical) -> type_id_int`）统一复用 `ugc_file_tools.node_graph_semantics.type_id_map`（单一真源），避免 pipeline 依赖写回实现域。

