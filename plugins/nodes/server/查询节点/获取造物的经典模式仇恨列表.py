from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取造物的经典模式仇恨列表",
    category="查询节点",
    inputs=[("造物实体", "实体")],
    outputs=[("仇恨列表", "实体列表")],
    description="获取造物的经典仇恨模式的仇恨列表，即仅仇恨配置为【默认类型】时，该节点才会有正确的输出列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取造物的经典模式仇恨列表(game, 造物实体):
    """获取造物的经典仇恨模式的仇恨列表，即仅仇恨配置为【默认类型】时，该节点才会有正确的输出列表"""
    return [game.create_mock_entity("仇恨目标1"), game.create_mock_entity("仇恨目标2")]
