from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询背包商店商品出售信息",
    category="查询节点",
    inputs=[("商店归属者实体", "实体"), ("商店序号", "整数"), ("道具配置ID", "配置ID")],
    outputs=[("出售货币字典", "字典"), ("排序优先级", "整数"), ("是否可出售", "布尔值")],
    description="查询背包商店种特定商品的出售信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询背包商店商品出售信息(game, 商店归属者实体, 商店序号, 道具配置ID):
    """查询背包商店种特定商品的出售信息"""
    return {"价格": 100, "库存": 10}
