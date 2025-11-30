from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据玩家序号获取玩家GUID",
    category="查询节点",
    inputs=[("玩家序号", "整数")],
    outputs=[("玩家GUID", "GUID")],
    description="根据玩家序号获取玩家GUID，玩家序号即该玩家为玩家几",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 根据玩家序号获取玩家GUID(game, 玩家序号):
    """根据玩家序号获取玩家GUID，玩家序号即该玩家为玩家几"""
    return f"player_{玩家序号}_guid"
