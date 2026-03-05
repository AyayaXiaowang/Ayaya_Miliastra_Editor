from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定阵营的实体列表",
    category="查询节点",
    inputs=[("目标实体列表", "实体列表"), ("阵营", "阵营")],
    outputs=[("结果列表", "实体列表")],
    description="在目标实体列表中获取归属于某个阵营的实体列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定阵营的实体列表(game, 目标实体列表, 阵营):
    """在目标实体列表中获取归属于某个阵营的实体列表"""
    desired = int(阵营)

    get_entity_id = getattr(game, "_get_entity_id", None)
    get_entity = getattr(game, "get_entity", None)
    get_custom = getattr(game, "get_custom_variable", None)

    out = []
    for item in list(目标实体列表 or []):
        entity_id = str(get_entity_id(item)) if callable(get_entity_id) else str(getattr(item, "entity_id", None) or item)
        ent = get_entity(entity_id) if callable(get_entity) else item
        if ent is None:
            continue

        # 最小语义：允许通过实体属性 camp 或自定义变量“阵营”注入阵营值；缺省视为 1。
        camp = getattr(ent, "camp", None)
        if camp is None and callable(get_custom):
            camp = get_custom(ent, "阵营", 1)
        if int(camp or 1) == desired:
            out.append(ent)
    return out
