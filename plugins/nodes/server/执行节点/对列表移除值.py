from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对列表移除值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("列表", "泛型列表"), ("移除序号", "整数")],
    outputs=[("流程出", "流程")],
    description="移除指定列表的指定序号位置的值。这会导致该序号后的所有值向前移动一位",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 对列表移除值(game, 列表, 移除序号):
    """移除指定列表的指定序号位置的值。这会导致该序号后的所有值向前移动一位"""
    if isinstance(列表, list) and 0 <= 移除序号 < len(列表):
        removed = 列表.pop(移除序号)
        log_info(f"[列表移除] 序号{移除序号}, 移除值: {removed}")
