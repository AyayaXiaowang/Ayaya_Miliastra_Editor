from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

_ENTITY_TYPE_OPTIONS = {
    "实体类型_关卡",
    "实体类型_物件",
    "实体类型_玩家",
    "实体类型_角色",
    "实体类型_造物",
}


def _infer_entity_type(game, entity) -> str:
    raw = getattr(entity, "entity_type", None)
    if isinstance(raw, str) and raw in _ENTITY_TYPE_OPTIONS:
        return raw

    get_custom = getattr(game, "get_custom_variable", None)
    if callable(get_custom):
        raw = get_custom(entity, "实体类型", None)
        if isinstance(raw, str) and raw in _ENTITY_TYPE_OPTIONS:
            return raw

    name = str(getattr(entity, "name", "") or "")
    if "关卡" in name or name == "自身实体":
        return "实体类型_关卡"
    if name.startswith("玩家"):
        return "实体类型_玩家"
    if name.startswith("角色") or name.startswith("敌人"):
        return "实体类型_角色"
    if ("造物" in name) or ("投射物" in name):
        return "实体类型_造物"
    return "实体类型_物件"


@node_spec(
    name="获取实体类型",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("实体类型", "枚举")],
    description="获取目标实体的实体类型",
    doc_reference="服务器节点/查询节点/查询节点.md",
    output_enum_options={
        "实体类型": [
            "实体类型_关卡",
            "实体类型_物件",
            "实体类型_玩家",
            "实体类型_角色",
            "实体类型_造物",
        ],
    },
)
def 获取实体类型(game, 目标实体):
    """获取目标实体的实体类型"""
    get_entity_id = getattr(game, "_get_entity_id", None)
    entity_id = str(get_entity_id(目标实体)) if callable(get_entity_id) else str(getattr(目标实体, "entity_id", None) or 目标实体)

    get_entity = getattr(game, "get_entity", None)
    ent = get_entity(entity_id) if callable(get_entity) else 目标实体
    if ent is None:
        return "实体类型_物件"
    return _infer_entity_type(game, ent)
