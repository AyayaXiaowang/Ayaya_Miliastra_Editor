from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询自定义商店商品出售信息",
    category="查询节点",
    inputs=[("商店归属者实体", "实体"), ("商店序号", "整数"), ("商品序号", "整数")],
    outputs=[("道具配置ID", "配置ID"), ("出售货币字典", "字典"), ("所属页签序号", "整数"), ("是否限购", "布尔值"), ("限购数量", "整数"), ("排序优先级", "整数"), ("是否可出售", "布尔值")],
    description="查询自定义商店特定商品的出售信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询自定义商店商品出售信息(game, 商店归属者实体, 商店序号, 商品序号):
    """查询自定义商店特定商品的出售信息"""
    return {"商品名": "特殊商品", "价格": 200}
