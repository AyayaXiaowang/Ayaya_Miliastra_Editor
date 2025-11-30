from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取列表对应值",
    category="查询节点",
    inputs=[("序号", "整数"), ("数据列表", "泛型")],
    outputs=[("结果", "泛型")],
    description="返回列表中指定序号对应的值。列表中序号从0开始",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取列表对应值(序号, 数据列表):
    """返回列表中指定序号对应的值。列表中序号从0开始"""
    if isinstance(数据列表, list) and 0 <= 序号 < len(数据列表):
        return 数据列表[序号]
    return None
