from __future__ import annotations

from typing import Optional, Set, TYPE_CHECKING

from engine.graph.models import EdgeModel, GraphModel, NodeModel
from engine.nodes.port_name_rules import get_dynamic_port_type
from engine.nodes.port_type_system import FLOW_PORT_TYPE
from engine.type_registry import (
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    is_dict_type_name,
    normalize_type_text,
)
from engine.utils.graph.graph_utils import is_flow_port_name

if TYPE_CHECKING:
    from engine.nodes.node_definition_loader import NodeDef
    from engine.nodes.node_registry import NodeRegistry


def _get_port_type_safe(node_def: "NodeDef", port_name: str, *, is_input: bool) -> str:
    """
    无异常版端口类型查询：
    - 优先显式类型；
    - 其次动态类型推断；
    - 流程端口兜底为 FLOW；
    - 缺失则返回空串。
    """
    type_dict = node_def.input_types if is_input else node_def.output_types
    port_name_text = str(port_name or "")
    if port_name_text in type_dict:
        return str(type_dict[port_name_text] or "")
    inferred = get_dynamic_port_type(port_name_text, type_dict, getattr(node_def, "dynamic_port_type", "") or "")
    if inferred:
        return str(inferred or "")
    if is_flow_port_name(port_name_text):
        return str(FLOW_PORT_TYPE)
    return ""


def _is_generic_family_type(type_name: object) -> bool:
    text = normalize_type_text(type_name)
    return text in {TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT}


def _resolve_node_def_for_node(node_registry: "NodeRegistry", node: NodeModel) -> Optional["NodeDef"]:
    category = str(getattr(node, "category", "") or "")
    name = str(getattr(node, "title", "") or "")
    if not category or not name:
        return None
    return node_registry.get_node_by_alias(category, name)


def _is_self_entity_query_node(node: NodeModel) -> bool:
    return (str(getattr(node, "category", "") or "") == "查询节点") and (str(getattr(node, "title", "") or "") == "获取自身实体")


def _edge_supported_by_local_var_relay(
    *,
    edge: EdgeModel,
    model: GraphModel,
    node_registry: "NodeRegistry",
    local_var_node_def: "NodeDef",
    local_var_input_port_name: str,
) -> bool:
    """
    判断该数据边是否适合插入【获取局部变量】中转。

    原则：
    - 若能从 src/dst 的端口类型或泛型约束推断出“可能的具体类型集合”，则要求与局部变量输入端口约束有交集；
    - 若无法推断（空集合），则保守返回 False（避免误插导致字典类型等校验错误）。
    """
    src_node = model.nodes.get(edge.src_node)
    dst_node = model.nodes.get(edge.dst_node)
    if src_node is None or dst_node is None:
        return False

    src_def = _resolve_node_def_for_node(node_registry, src_node)
    dst_def = _resolve_node_def_for_node(node_registry, dst_node)
    if src_def is None or dst_def is None:
        return False

    src_type = _get_port_type_safe(src_def, str(edge.src_port), is_input=False)
    dst_type = _get_port_type_safe(dst_def, str(edge.dst_port), is_input=True)

    # 明确字典：直接跳过（局部变量禁止字典类型）
    if is_dict_type_name(src_type) or is_dict_type_name(dst_type):
        return False
    if normalize_type_text(src_type) == TYPE_GENERIC_DICT or normalize_type_text(dst_type) == TYPE_GENERIC_DICT:
        return False

    src_candidates: Set[str] = set()
    dst_candidates: Set[str] = set()

    if src_type and not _is_generic_family_type(src_type):
        src_candidates.add(str(src_type))
    else:
        src_candidates.update(src_def.get_generic_constraints(str(edge.src_port), is_input=False))

    if dst_type and not _is_generic_family_type(dst_type):
        dst_candidates.add(str(dst_type))
    else:
        dst_candidates.update(dst_def.get_generic_constraints(str(edge.dst_port), is_input=True))

    if src_candidates and dst_candidates:
        edge_candidates = src_candidates & dst_candidates
    else:
        edge_candidates = src_candidates or dst_candidates

    if not edge_candidates:
        return False

    allowed_by_local_var = set(local_var_node_def.get_generic_constraints(local_var_input_port_name, is_input=True))
    if not allowed_by_local_var:
        # 节点定义缺失约束时不做额外限制，但仍需防御字典类型
        return True

    return bool(edge_candidates & allowed_by_local_var)


__all__ = [
    "_edge_supported_by_local_var_relay",
    "_is_self_entity_query_node",
]



