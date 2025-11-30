from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="向自定义商店出售表中新增商品",
    category="执行节点",
    inputs=[("流程入", "流程"), ("商店归属者实体", "实体"), ("商店序号", "整数"), ("商品道具配置ID", "配置ID"), ("出售货币字典", "字典"), ("所属页签序号", "整数"), ("是否限购", "布尔值"), ("限购数量", "整数"), ("排序优先级", "整数"), ("是否可出售", "布尔值")],
    outputs=[("流程出", "流程"), ("商品索引", "整数")],
    description="向自定义商店出售表中新增商品，新增成功后出参会生成一个整数型索引作为该商品的标识",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 向自定义商店出售表中新增商品(game, 商店归属者实体, 商店序号, 商品道具配置ID, 出售货币字典, 所属页签序号, 是否限购, 限购数量, 排序优先级, 是否可出售):
    """向自定义商店出售表中新增商品，新增成功后出参会生成一个整数型索引作为该商品的标识"""
    return None  # 商品索引
