from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="装备指定序号添加词条",
    category="执行节点",
    inputs=[("流程入", "流程"), ("装备索引", "整数"), ("词条配置ID", "配置ID"), ("插入序号", "整数"), ("是否覆写词条值", "布尔值"), ("词条数值", "浮点数")],
    outputs=[("流程出", "流程")],
    description="对指定装备实例的指定词条序号位置添加预先配置好的词条，可以覆写词条的数值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 装备指定序号添加词条(game, 装备索引, 词条配置ID, 插入序号, 是否覆写词条值, 词条数值):
    """对指定装备实例的指定词条序号位置添加预先配置好的词条，可以覆写词条的数值"""
    log_info(f"[装备指定序号添加词条] 执行")
