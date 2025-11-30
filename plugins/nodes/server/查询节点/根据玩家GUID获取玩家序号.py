from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据玩家GUID获取玩家序号",
    category="查询节点",
    inputs=[("玩家GUID", "GUID")],
    outputs=[("玩家序号", "整数")],
    description="根据玩家GUID获取玩家序号，玩家序号即该玩家为玩家几",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 根据玩家GUID获取玩家序号(game, 玩家GUID):
    """根据玩家GUID获取玩家序号，玩家序号即该玩家为玩家几"""
    return 1
