from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="向背包商店出售表中新增商品",
    category="执行节点",
    inputs=[("流程入", "流程"), ("商店归属者实体", "实体"), ("商店序号", "整数"), ("商品道具配置ID", "配置ID"), ("出售货币字典", "字典"), ("所属页签序号", "整数"), ("排序优先级", "整数"), ("是否可出售", "布尔值")],
    outputs=[("流程出", "流程")],
    description="向背包商店出售表中新增商品",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 向背包商店出售表中新增商品(game, 商店归属者实体, 商店序号, 商品道具配置ID, 出售货币字典, 所属页签序号, 排序优先级, 是否可出售):
    """向背包商店出售表中新增商品"""
    log_info(f"[向背包商店出售表中新增商品] 执行")
