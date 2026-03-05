from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取指定元件ID的实体列表",
    category="查询节点",
    inputs=[("目标实体列表", "实体列表"), ("元件ID", "元件ID")],
    outputs=[("结果列表", "实体列表")],
    description="在目标实体列表中获取以指定元件ID创建的实体列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取指定元件ID的实体列表(game, 目标实体列表, 元件ID):
    """在目标实体列表中获取以指定元件ID创建的实体列表"""
    desired = int(元件ID)

    get_entity_id = getattr(game, "_get_entity_id", None)
    get_entity = getattr(game, "get_entity", None)

    def _resolve_component_id(ent) -> int | None:
        raw = getattr(ent, "component_id", None)
        if raw is not None:
            return int(raw)
        name = str(getattr(ent, "name", "") or "")
        if name.startswith("元件_"):
            tail = name[len("元件_") :].strip()
            if tail.isdigit():
                return int(tail)
        return None

    out = []
    for item in list(目标实体列表 or []):
        entity_id = str(get_entity_id(item)) if callable(get_entity_id) else str(getattr(item, "entity_id", None) or item)
        ent = get_entity(entity_id) if callable(get_entity) else item
        if ent is None:
            continue
        if _resolve_component_id(ent) == desired:
            out.append(ent)
    return out
