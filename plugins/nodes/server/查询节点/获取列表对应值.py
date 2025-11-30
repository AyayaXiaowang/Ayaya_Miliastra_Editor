from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取列表对应值",
    category="查询节点",
    inputs=[("列表", "泛型"), ("序号", "整数")],
    outputs=[("值", "泛型")],
    description="返回列表中指定序号对应的值，序号从0开始",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取列表对应值(列表, 序号):
    """返回列表中指定序号对应的值，序号从0开始"""
    if isinstance(列表, list) and 0 <= 序号 < len(列表):
        return 列表[序号]
    return None
