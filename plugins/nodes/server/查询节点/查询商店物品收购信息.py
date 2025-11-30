from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询商店物品收购信息",
    category="查询节点",
    inputs=[("商店归属者实体", "实体"), ("商店序号", "整数"), ("道具配置ID", "配置ID")],
    outputs=[("收购货币字典", "字典"), ("是否可收购", "布尔值")],
    description="查询商店特定物品的收购信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询商店物品收购信息(game, 商店归属者实体, 商店序号, 道具配置ID):
    """查询商店特定物品的收购信息"""
    return {"价格": 50, "限购": 99}
