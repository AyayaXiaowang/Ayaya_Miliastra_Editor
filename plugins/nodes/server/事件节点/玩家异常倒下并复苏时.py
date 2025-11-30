from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家异常倒下并复苏时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("玩家实体", "实体")],
    description="角色因溺水、坠入深渊等原因倒下并复苏时，玩家实体上触发该事件",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 玩家异常倒下并复苏时(game):
    """角色因溺水、坠入深渊等原因倒下并复苏时，玩家实体上触发该事件"""
    玩家 = game.create_mock_entity("玩家1")
    return 玩家
