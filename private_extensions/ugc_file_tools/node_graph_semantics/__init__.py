"""
ugc_file_tools.node_graph_semantics

节点图共享语义层（供 `.gia` 导出 与 `.gil` 写回共同复用）。

原则：
- 只放纯规则/编码构件（不含 pipeline/IO/UI）。
- 允许依赖 `ugc_file_tools.contracts`（跨域契约层）。
- 禁止反向依赖 `gia_export.*` / `node_graph_writeback.*`，避免循环引用与边界坍塌。
"""

