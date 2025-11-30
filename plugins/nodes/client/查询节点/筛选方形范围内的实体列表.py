from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="筛选方形范围内的实体列表",
    category="查询节点",
    inputs=[("宽度", "浮点数"), ("高度", "浮点数"), ("长度", "浮点数"), ("中心位置", "三维向量"), ("筛选数量上限", "整数"), ("筛选规则", "枚举")],
    outputs=[("筛选结果", "实体列表")],
    description="以特定的规则和数量上限筛选在方形范围内的实体，满足条件的实体会组成实体列表输出",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 筛选方形范围内的实体列表(宽度, 高度, 长度, 中心位置, 筛选数量上限, 筛选规则):
    """以特定的规则和数量上限筛选在方形范围内的实体，满足条件的实体会组成实体列表输出"""
    return None  # 筛选结果
