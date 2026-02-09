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
    # 本地测试（MockRuntime）最小语义：允许用自定义变量注入；未设置时回退为 0。
    get_custom = getattr(game, "get_custom_variable", None)
    if not callable(get_custom):
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    暴击率 = float(get_custom(目标实体, "暴击率", 0.0) or 0.0)
    暴击伤害 = float(get_custom(目标实体, "暴击伤害", 0.0) or 0.0)
    治疗加成 = float(get_custom(目标实体, "治疗加成", 0.0) or 0.0)
    受治疗加成 = float(get_custom(目标实体, "受治疗加成", 0.0) or 0.0)
    元素充能效率 = float(get_custom(目标实体, "元素充能效率", 0.0) or 0.0)
    冷却缩减 = float(get_custom(目标实体, "冷却缩减", 0.0) or 0.0)
    护盾强效 = float(get_custom(目标实体, "护盾强效", 0.0) or 0.0)
    return 暴击率, 暴击伤害, 治疗加成, 受治疗加成, 元素充能效率, 冷却缩减, 护盾强效
