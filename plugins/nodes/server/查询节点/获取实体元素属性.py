from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体元素属性",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("火元素伤害加成", "浮点数"), ("火元素抗性", "浮点数"), ("水元素伤害加成", "浮点数"), ("水元素抗性", "浮点数"), ("草元素伤害加成", "浮点数"), ("草元素抗性", "浮点数"), ("雷元素伤害加成", "浮点数"), ("雷元素抗性", "浮点数"), ("风元素伤害加成", "浮点数"), ("风元素抗性", "浮点数"), ("冰元素伤害加成", "浮点数"), ("冰元素抗性", "浮点数"), ("岩元素伤害加成", "浮点数"), ("岩元素抗性", "浮点数"), ("物理伤害加成", "浮点数"), ("物理抗性", "浮点数")],
    description="获取目标实体的元素相关属性",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体元素属性(game, 目标实体):
    """获取目标实体的元素相关属性"""
    return None  # Mock返回
