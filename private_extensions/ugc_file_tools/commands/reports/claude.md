# ugc_file_tools/commands/reports 目录说明

## 目录用途

- 收口 **报告/覆盖率/差异对照** 类命令入口（通常以 `report_*.py` 命名）。
- 输出产物一律写入 `ugc_file_tools/out/`（由 `output_paths.py` 收口），不污染项目存档目录。

## 当前状态

- 本目录脚本原则上只做 CLI 参数解析 + 调用实现函数 + 落盘报告。
- 与写回/导出链路的“口径契约”应复用既有模块（例如 `graph/model_ir.py`、`node_graph_writeback/*`），避免在单脚本内复制适配逻辑。
- 目前包含：
  - `report_graph_writeback_gaps`（写回覆盖差异报告；实现位于本目录）
  - `report_gia_vs_gil_graph_ir_diff`（GIA 导出 vs GIL 写回：Graph IR 口径差异报告；用于批量定位“导出/写回分叉”）
  - `report_gil_payload_graph_ir_diff`（GIL vs GIL：payload Graph IR 对照报告；输出 graphs/edges/pins/graph_variables 差异与 missing pins 聚类摘要，用于定位“游戏处理后导出 vs 工具直接处理”的结构差异）
  - `report_gil_dump_json_diff`（GIL vs GIL：dump-json(payload 数值键 JSON) 深度 diff；按路径列出差异点，可选落盘两侧 dump-json 作为证据快照）
  - `report_gil_payload_root_wire_sections_diff`（GIL vs GIL：payload_root wire-level section bytes 对照；按 field_number 对比 length-delimited payload 是否完全一致，用于证明是否发生 payload drift）
  - `report_node_template_coverage_diff`（节点模板覆盖差异）
  - `report_node_graph_writeback_coverage`（模板样本覆盖统计）
  - `report_node_type_semantic_map_*`（映射覆盖/无效节点/对照 genshin-ts）
  - `report_graph_variable_truth_diff`（真源图变量类型对照）

## 注意事项

- 不使用 `try/except`；报告生成失败直接抛错（fail-fast）。
- 路径计算统一使用 `ugc_file_tools.repo_paths` / `ugc_file_tools.output_paths`，禁止硬编码 `out/` 相对路径。
- 报告端口类型证据读取优先 `*_port_types`，缺失时回退 `effective_*_types`（兼容仅携带 GraphModel 快照字段的 JSON 形态）。