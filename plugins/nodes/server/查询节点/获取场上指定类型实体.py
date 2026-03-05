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
    # 1) 显式标注优先（用于本地测试注入）
    raw = getattr(entity, "entity_type", None)
    if isinstance(raw, str) and raw in _ENTITY_TYPE_OPTIONS:
        return raw

    # 2) 允许通过自定义变量注入（避免修改 MockEntity 结构）
    get_custom = getattr(game, "get_custom_variable", None)
    if callable(get_custom):
        raw = get_custom(entity, "实体类型", None)
        if isinstance(raw, str) and raw in _ENTITY_TYPE_OPTIONS:
            return raw

    # 3) 兜底：按名称做启发式推断（最小可用语义）
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
    name="获取场上指定类型实体",
    category="查询节点",
    inputs=[("实体类型", "枚举")],
    outputs=[("实体列表", "实体列表")],
    description="获取当前场上指定类型的所有实体，该实体列表的数量可能会较大",
    doc_reference="服务器节点/查询节点/查询节点.md",
    input_enum_options={
        "实体类型": [
            "实体类型_关卡",
            "实体类型_物件",
            "实体类型_玩家",
            "实体类型_角色",
            "实体类型_造物",
        ],
    },
)
def 获取场上指定类型实体(game, 实体类型):
    """获取当前场上指定类型的所有实体，该实体列表的数量可能会较大"""
    get_all_entities = getattr(game, "get_all_entities", None)
    if callable(get_all_entities):
        all_entities = list(get_all_entities())
    else:
        all_entities = list(getattr(game, "entities", {}).values())

    desired = str(实体类型 or "")
    if desired not in _ENTITY_TYPE_OPTIONS:
        return []
    return [e for e in all_entities if _infer_entity_type(game, e) == desired]
