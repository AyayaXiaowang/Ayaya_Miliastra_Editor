from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_其他节点_impl_helpers import *


@node_spec(
    name="节点图结束（整数）",
    category="其他节点",
    inputs=[("结果", "整数")],
    outputs=[],
    description="整数过滤器节点图的结束节点（纯数据节点）：用于承载本图最终输出的整数值。",
    doc_reference="客户端节点/其他节点/其他节点.md",
)
def 节点图结束_整数(结果):
    """整数过滤器节点图的结束节点（纯数据节点）。"""
    return


