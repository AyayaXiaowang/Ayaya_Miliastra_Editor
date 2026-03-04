# ugc_file_tools/builtin_resources/template_library/test2_client_writeback_samples 目录说明

## 目录用途
- 存放 `test2/client` 写回链路所需的**最小模板样本库**（仅 `.gil`），用于：
  - `report_graph_writeback_gaps` 覆盖诊断（client scope）
  - `graph_model_json_to_gil_node_graph` 写回（client scope）

## 当前状态
- 该目录仅包含“已验证可解析”的 client `.gil`：
  - 用于提供 client 图段结构模板的最小样本（含一张 client 图）。
  - 用于补齐 client 节点模板与 record 覆盖的“缺失节点墙”样本（含批量节点与 auto-wire records）。
- 主要样本文件（稳定可脚本引用）：
  - `node_graph_notify_server.gil`：client scope 的“通知服务器”节点图样本。
  - `missing_nodes_wall_test2_client_autowired.gil`：client 的缺失节点墙（auto-wire 覆盖）。

## 注意事项
- 该目录作为 `--template-library-dir` 输入，建议保持内容稳定；新增样本前先用 `report_graph_writeback_gaps` 扫描验证可解析。
- 不建议混入与 client 写回无关的存档，避免模板竞争与扫描噪声。