from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="打开商店",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("商店归属者实体", "实体"), ("商店序号", "整数")],
    outputs=[("流程出", "流程")],
    description="在游戏运行过程中以玩家实体的视角打开商店",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 打开商店(game, 玩家实体, 商店归属者实体, 商店序号):
    """在游戏运行过程中以玩家实体的视角打开商店"""
    log_info(f"[打开商店] 执行")
