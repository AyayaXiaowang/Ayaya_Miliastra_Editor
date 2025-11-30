from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体进阶属性",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("暴击率", "浮点数"), ("暴击伤害", "浮点数"), ("治疗加成", "浮点数"), ("受治疗加成", "浮点数"), ("元素充能效率", "浮点数"), ("冷却缩减", "浮点数"), ("护盾强效", "浮点数")],
    description="获取实体的进阶属性",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体进阶属性(game, 目标实体):
    """获取实体的进阶属性"""
    return None  # Mock返回
