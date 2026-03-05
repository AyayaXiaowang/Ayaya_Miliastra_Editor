# ugc_file_tools/builtin_resources/template_library/test2_server_writeback_samples 目录说明

## 目录用途
- 存放 `test2/server` 写回链路所需的**最小模板样本库**（仅 `.gil`），用于：
  - `report_graph_writeback_gaps` 覆盖诊断
  - `graph_model_json_to_gil_node_graph` 模板克隆模式写回

## 当前状态
- 该目录仅包含“已验证可解析”的 `.gil`：
  - 来自 `save/示范存档` 的最小参考样本（补齐少量节点模板/结构性 record）。
  - 来自“缺失节点墙/直接导出”的覆盖样本（补齐大量 node type_id 模板与多数 data-link 结构）。
  - 来自 auto-wire 的补丁样本（补齐少量残留的 data-link slot 与 OutParam 模板）。
- 主要样本文件（稳定可脚本引用）：
  - `01_ng_minimal_wiring_graph_var_set_entity.gil`：最小连线 + 图变量 set_entity。
  - `02_graph_vars_all_types_minimal.gil`：图变量全类型最小参考。
  - `03_node_graph_new_empty.gil`：新建空图（用于 base 容器/对照）。
  - `04_struct_var_with_defaults_minimal.gil`：结构体变量（带默认值）最小示范。
  - `05_signals_create_and_use_minimal.gil`：信号创建与使用最小示范。
  - `06_signals_multi_param_semantic_generated.gil`：多类型参数信号（语义生成）示范。
  - `07_struct_defs_all_field_types_writeback_demo.gil`：结构体全类型字段写回示范。
  - `direct_export_smoke_test.gil`：直接导出 smoke test（覆盖导出段结构）。
  - `autowire_templates_test2_server_direct_export_v2.gil`：auto-wire 模板覆盖样本（direct export v2）。

## 注意事项
- 该目录作为 `--template-library-dir` 输入，建议保持内容稳定；若替换/新增样本，请确保先能被 `report_graph_writeback_gaps` 正常扫描。
- 不建议混入与本场景无关的存档（例如 UI/结构体大集合），避免扫描变慢或引入不必要的模板竞争。