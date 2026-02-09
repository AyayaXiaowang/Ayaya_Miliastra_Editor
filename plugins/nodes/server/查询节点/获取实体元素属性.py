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
    # 本地测试（MockRuntime）最小语义：允许用自定义变量注入；未设置时回退为 0。
    get_custom = getattr(game, "get_custom_variable", None)
    if not callable(get_custom):
        return (0.0,) * 16

    火元素伤害加成 = float(get_custom(目标实体, "火元素伤害加成", 0.0) or 0.0)
    火元素抗性 = float(get_custom(目标实体, "火元素抗性", 0.0) or 0.0)
    水元素伤害加成 = float(get_custom(目标实体, "水元素伤害加成", 0.0) or 0.0)
    水元素抗性 = float(get_custom(目标实体, "水元素抗性", 0.0) or 0.0)
    草元素伤害加成 = float(get_custom(目标实体, "草元素伤害加成", 0.0) or 0.0)
    草元素抗性 = float(get_custom(目标实体, "草元素抗性", 0.0) or 0.0)
    雷元素伤害加成 = float(get_custom(目标实体, "雷元素伤害加成", 0.0) or 0.0)
    雷元素抗性 = float(get_custom(目标实体, "雷元素抗性", 0.0) or 0.0)
    风元素伤害加成 = float(get_custom(目标实体, "风元素伤害加成", 0.0) or 0.0)
    风元素抗性 = float(get_custom(目标实体, "风元素抗性", 0.0) or 0.0)
    冰元素伤害加成 = float(get_custom(目标实体, "冰元素伤害加成", 0.0) or 0.0)
    冰元素抗性 = float(get_custom(目标实体, "冰元素抗性", 0.0) or 0.0)
    岩元素伤害加成 = float(get_custom(目标实体, "岩元素伤害加成", 0.0) or 0.0)
    岩元素抗性 = float(get_custom(目标实体, "岩元素抗性", 0.0) or 0.0)
    物理伤害加成 = float(get_custom(目标实体, "物理伤害加成", 0.0) or 0.0)
    物理抗性 = float(get_custom(目标实体, "物理抗性", 0.0) or 0.0)

    return (
        火元素伤害加成,
        火元素抗性,
        水元素伤害加成,
        水元素抗性,
        草元素伤害加成,
        草元素抗性,
        雷元素伤害加成,
        雷元素抗性,
        风元素伤害加成,
        风元素抗性,
        冰元素伤害加成,
        冰元素抗性,
        岩元素伤害加成,
        岩元素抗性,
        物理伤害加成,
        物理抗性,
    )
