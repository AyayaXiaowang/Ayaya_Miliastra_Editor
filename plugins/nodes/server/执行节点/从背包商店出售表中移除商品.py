from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="从背包商店出售表中移除商品",
    category="执行节点",
    inputs=[("流程入", "流程"), ("商店归属者实体", "实体"), ("商店序号", "整数"), ("道具配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="从背包商店出售表中移除商品",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 从背包商店出售表中移除商品(game, 商店归属者实体, 商店序号, 道具配置ID):
    """从背包商店出售表中移除商品"""
    log_info(f"[从背包商店出售表中移除商品] 执行")
