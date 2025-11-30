from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="从物品收购表中移除物品",
    category="执行节点",
    inputs=[("流程入", "流程"), ("商店归属者实体", "实体"), ("商店序号", "整数"), ("商品道具配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="从物品收购表中移除物品",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 从物品收购表中移除物品(game, 商店归属者实体, 商店序号, 商品道具配置ID):
    """从物品收购表中移除物品"""
    log_info(f"[从物品收购表中移除物品] 执行")
