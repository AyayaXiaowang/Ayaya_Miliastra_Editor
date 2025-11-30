from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改物品收购表中道具收购信息",
    category="执行节点",
    inputs=[("流程入", "流程"), ("商店归属者实体", "实体"), ("商店序号", "整数"), ("商品道具配置ID", "配置ID"), ("收购货币字典", "字典"), ("是否可收购", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改物品收购表中道具收购信息",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改物品收购表中道具收购信息(game, 商店归属者实体, 商店序号, 商品道具配置ID, 收购货币字典, 是否可收购):
    """修改物品收购表中道具收购信息"""
    log_info(f"[修改物品收购表中道具收购信息] 执行")
