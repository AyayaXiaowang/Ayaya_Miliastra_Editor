from __future__ import annotations

"""
ugc_file_tools.node_graph_writeback

GraphModel(JSON) → `.gil` 节点图段写回的模块化实现。

注意：
- 对外入口仍以 `ugc_file_tools/graph_model_json_to_gil_node_graph.py` 为主（包含 CLI 与兼容层）。
- 这里按职责拆分底层编码/解析/变量/枚举/写回逻辑，便于维护与单测/复用。
"""

def write_graph_model_to_gil(*args, **kwargs):  # type: ignore[no-untyped-def]
    """
    对外稳定入口（lazy import）：
    - 避免 `ugc_file_tools.gia_export.*` 与 `node_graph_writeback.*` 的循环引用在 import 阶段触发；
    - 真实实现位于 `writer.write_graph_model_to_gil`。
    """
    from .writer import write_graph_model_to_gil as _impl

    return _impl(*args, **kwargs)


__all__ = ["write_graph_model_to_gil"]


