from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取造物当前目标",
    category="查询节点",
    inputs=[("造物实体", "实体")],
    outputs=[("目标实体", "实体")],
    description="根据造物当前行为的不同，目标实体也不尽相同。 例如当造物在攻击敌方时，造物的目标为敌方指定实体。 例如当造物在对友方进行治疗时，造物的目标为友方指定实体。",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取造物当前目标(game, 造物实体):
    """根据造物当前行为的不同，目标实体也不尽相同。 例如当造物在攻击敌方时，造物的目标为敌方指定实体。 例如当造物在对友方进行治疗时，造物的目标为友方指定实体。"""
    return game.create_mock_entity("目标实体")
