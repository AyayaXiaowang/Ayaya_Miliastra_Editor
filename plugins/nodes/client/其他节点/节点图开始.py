from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_其他节点_impl_helpers import *


@node_spec(
    name="节点图开始",
    category="其他节点",
    inputs=[],
    outputs=[("流程出", "流程")],
    description="技能节点图的开始事件：仅提供一个流程出口，不做任何额外逻辑。在该节点之后按顺序连接其它节点实现技能效果。",
    doc_reference="客户端节点/其他节点/其他节点.md",
)
def 节点图开始(game):
    """技能节点图的开始事件：仅提供一个流程出口，不做任何额外逻辑。"""
    return
