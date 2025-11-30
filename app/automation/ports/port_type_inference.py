# -*- coding: utf-8 -*-
"""
port_type_inference: 端口类型推断工具
从 port_type_setter.py 提取的类型推断逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, List, Any, Tuple

from app.automation.ports._type_utils import infer_type_from_value
from engine.graph.models.graph_model import GraphModel, NodeModel


# 基础类型 → 列表类型映射
BASE_TO_LIST_MAP: Dict[str, str] = {
    "实体": "实体列表",
    "GUID": "GUID列表",
    "整数": "整数列表",
    "布尔值": "布尔值列表",
    "浮点数": "浮点数列表",
    "字符串": "字符串列表",
    "三维向量": "三维向量列表",
    "元件ID": "元件ID列表",
    "配置ID": "配置ID列表",
}

# 列表类型 → 基础类型映射
LIST_TO_BASE_MAP: Dict[str, str] = {v: k for k, v in BASE_TO_LIST_MAP.items()}


@dataclass(frozen=True)
class EdgeLookup:
    incoming: Dict[str, Dict[str, List[Any]]]
    outgoing: Dict[str, Dict[str, List[Any]]]


def build_port_type_overrides(graph_model: GraphModel) -> Dict[str, Dict[str, str]]:
    """标准化 GraphModel.metadata['port_type_overrides'] 结构.

    说明：
    - 将 metadata 中的端口类型覆盖信息收敛为 {node_id: {port_name: type_text}} 形式；
    - 仅保留 key/value 均为字符串的条目，避免后续使用时做重复类型判断；
    - 不在此处做“去泛型/去流程”过滤，由调用方按各自语义决定是否忽略。
    """
    overrides_result: Dict[str, Dict[str, str]] = {}
    metadata_obj = getattr(graph_model, "metadata", {}) or {}
    overrides_raw = metadata_obj.get("port_type_overrides")
    if not isinstance(overrides_raw, dict):
        return overrides_result

    for node_key, mapping in overrides_raw.items():
        if not isinstance(node_key, str) or not isinstance(mapping, dict):
            continue
        normalized_mapping: Dict[str, str] = {}
        for port_name, type_text in mapping.items():
            if not isinstance(port_name, str) or not isinstance(type_text, str):
                continue
            normalized_mapping[port_name] = type_text
        if normalized_mapping:
            overrides_result[node_key] = normalized_mapping

    return overrides_result


def build_edge_lookup(graph_model: GraphModel) -> EdgeLookup:
    """构建节点入/出边的索引，加速类型推断阶段的查询。"""
    incoming: Dict[str, Dict[str, List[Any]]] = {}
    outgoing: Dict[str, Dict[str, List[Any]]] = {}
    for edge in getattr(graph_model, "edges", {}).values():
        incoming.setdefault(edge.dst_node, {}).setdefault(edge.dst_port, []).append(edge)
        outgoing.setdefault(edge.src_node, {}).setdefault(edge.src_port, []).append(edge)
    return EdgeLookup(incoming=incoming, outgoing=outgoing)


def normalize_node_id_for_overrides(node_id: object) -> str:
    """将可能带有 copy_block 后缀的节点 ID 归一化为原始节点 ID。

    例如：
        "node_以键查询字典值_446c5c6c_copy_block_2_1" → "node_以键查询字典值_446c5c6c"
    """
    if not isinstance(node_id, str):
        return ""

    raw_id_text = node_id.strip()
    if raw_id_text == "":
        return ""

    marker_text = "_copy_block_"
    marker_index = raw_id_text.find(marker_text)
    if marker_index > 0:
        return raw_id_text[:marker_index]
    return raw_id_text


def get_node_port_type_overrides_for_id(
    overrides_mapping: Dict[str, Dict[str, str]],
    node_identifier: object,
) -> Optional[Dict[str, str]]:
    """根据节点 ID 获取端口类型覆盖信息，自动兼容 copy_block 节点。

    查找顺序：
    1）尝试以完整 ID 精确匹配；
    2）若未命中，则将 ID 归一化为“去掉 _copy_block_ 后缀”的形式再查找。
    """
    if not isinstance(overrides_mapping, dict):
        return None
    if not isinstance(node_identifier, str):
        return None

    direct_mapping = overrides_mapping.get(node_identifier)
    if isinstance(direct_mapping, Dict):
        return direct_mapping

    normalized_id = normalize_node_id_for_overrides(node_identifier)
    if normalized_id and normalized_id != node_identifier:
        base_mapping = overrides_mapping.get(normalized_id)
        if isinstance(base_mapping, Dict):
            return base_mapping

    return None


def parse_typed_dict_alias(type_name: object) -> tuple[bool, str, str]:
    """解析类似“字符串_GUID列表字典”或“字符串-GUID列表字典”的别名字典类型。

    约定格式：
    - 统一以“字典”结尾，例如：`字符串_GUID列表字典` 或 `字符串-GUID列表字典`
    - 以第一个“-”或“_”划分键/值类型名：左侧为键类型，右侧为值类型
    - 键/值类型名本身必须是已有的合法类型名（例如：整数、字符串、GUID列表等）
    """
    if not isinstance(type_name, str):
        return False, "", ""

    text = type_name.strip()
    if not text or not text.endswith("字典"):
        return False, "", ""

    body = text[: -len("字典")].strip()
    if not body:
        return False, "", ""

    dash_index = body.find("-")
    underscore_index = body.find("_")

    separator_index = -1
    if dash_index >= 0 and underscore_index >= 0:
        separator_index = min(dash_index, underscore_index)
    elif dash_index >= 0:
        separator_index = dash_index
    else:
        separator_index = underscore_index

    if separator_index <= 0 or separator_index >= len(body) - 1:
        return False, "", ""

    key_raw = body[:separator_index]
    value_raw = body[separator_index + 1 :]
    key_type = key_raw.strip()
    value_type = value_raw.strip()
    if not key_type or not value_type:
        return False, "", ""

    return True, key_type, value_type


def _iter_incoming_edges(
    node_id: str,
    port_name: str,
    graph_model: GraphModel,
    edge_lookup: EdgeLookup | None,
) -> List[Any]:
    if edge_lookup is not None:
        return edge_lookup.incoming.get(node_id, {}).get(port_name, [])
    return [
        edge
        for edge in getattr(graph_model, "edges", {}).values()
        if edge.dst_node == node_id and edge.dst_port == port_name
    ]


def _iter_outgoing_edges(
    node_id: str,
    port_name: str,
    graph_model: GraphModel,
    edge_lookup: EdgeLookup | None,
) -> List[Any]:
    if edge_lookup is not None:
        return edge_lookup.outgoing.get(node_id, {}).get(port_name, [])
    return [
        edge
        for edge in getattr(graph_model, "edges", {}).values()
        if edge.src_node == node_id and edge.src_port == port_name
    ]


def is_generic_type_name(type_name: object) -> bool:
    """判定是否为"泛型家族"类型名。
    
    泛型家族包括：泛型、泛型列表、泛型字典等。
    
    Args:
        type_name: 类型名称
    
    Returns:
        True表示是泛型家族
    """
    if not isinstance(type_name, str):
        return False
    
    text = type_name.strip()
    if text == "" or text == "泛型" or text.startswith("泛型"):
        return True
    return False


def is_flow_type_name(type_name: object) -> bool:
    """判定是否为“流程”类型名。

    说明：
    - 仅在数据端口类型推断阶段使用，将“流程”视为无效候选；
    - 流程端口本身不会通过本模块参与数据类型推断。
    """
    if not isinstance(type_name, str):
        return False
    return type_name.strip() == "流程"


def upgrade_to_list_type(declared_type: str, inferred_scalar: Optional[str]) -> Optional[str]:
    """当端口声明为列表类而值类型推断为基础标量时，提升为对应列表类型。
    
    Args:
        declared_type: 端口声明的类型
        inferred_scalar: 从值推断出的基础标量类型
    
    Returns:
        提升后的类型或原类型
    """
    if not isinstance(declared_type, str) or not isinstance(inferred_scalar, str) or inferred_scalar == "":
        return inferred_scalar
    
    # 仅当"明确为列表类（含 泛型列表）"时，才将基础标量派生为对应"X列表"
    if ("列表" in declared_type) or (declared_type.strip() == "泛型列表"):
        return BASE_TO_LIST_MAP.get(inferred_scalar, inferred_scalar)
    
    return inferred_scalar


def derive_concrete_type_from_source_node(
    source_node: NodeModel,
    source_node_def,
    source_port_name: str,
    graph_model: GraphModel,
    executor,
    *,
    edge_lookup: EdgeLookup | None = None,
) -> Optional[str]:
    """从源节点派生具体类型（当源端口为泛型家族时）。
    
    尝试基于"源节点的输入常量"和"上游非泛型入边"推断具体类型。
    
    Args:
        source_node: 源节点模型
        source_node_def: 源节点定义
        source_port_name: 源端口名称
        graph_model: 图模型
        executor: 执行器实例（用于获取节点定义）
    
    Returns:
        派生出的具体类型，失败返回None
    """
    if source_node is None or source_node_def is None or not isinstance(source_port_name, str):
        return None

    # 0) 优先：若 GraphModel.metadata 中存在端口类型覆盖信息，则直接采用
    overrides = build_port_type_overrides(graph_model)
    source_node_id = getattr(source_node, "id", "")
    node_overrides = get_node_port_type_overrides_for_id(overrides, source_node_id)
    if isinstance(node_overrides, dict):
        override_raw = node_overrides.get(source_port_name)
        if isinstance(override_raw, str):
            override_type = override_raw.strip()
            if override_type and (not is_generic_type_name(override_type)) and (not is_flow_type_name(override_type)):
                return override_type

    declared_output = source_node_def.get_port_type(source_port_name, is_input=False)
    is_list_like = False
    if isinstance(declared_output, str):
        text = declared_output.strip()
        is_list_like = ("列表" in text) or (text == "泛型列表")
    
    # 1) 先看源节点的输入常量
    constants_map = dict(getattr(source_node, "input_constants", {}) or {})
    if constants_map:
        scalar_candidates: List[str] = []
        for input_name, value in constants_map.items():
            base = infer_type_from_value(str(value))
            if isinstance(base, str) and base.strip() != "" and (not is_generic_type_name(base)):
                scalar_candidates.append(base)
        
        if len(scalar_candidates) > 0:
            base_pick = list(dict.fromkeys(scalar_candidates))[0]
            if is_list_like:
                mapped = BASE_TO_LIST_MAP.get(base_pick, base_pick)
                if not is_generic_type_name(mapped):
                    return mapped
            else:
                if not is_generic_type_name(base_pick):
                    return base_pick
    
    # 2) 若无常量或未得出，尝试基于"源节点的入边源端口类型"做一次收敛（仅取非泛型候选）
    non_generic_inputs: List[str] = []
    incoming_edges: List[Any] = []
    if edge_lookup is not None:
        buckets = edge_lookup.incoming.get(getattr(source_node, "id", ""), {})
        for edges in buckets.values():
            incoming_edges.extend(edges)
    else:
        incoming_edges = [
            edge
            for edge in getattr(graph_model, "edges", {}).values()
            if edge.dst_node == getattr(source_node, "id", "")
        ]

    for edge in incoming_edges:
        upstream_node = graph_model.nodes.get(edge.src_node)
        if upstream_node is None:
            continue
        upstream_def = executor._get_node_def_for_model(upstream_node)
        if upstream_def is None:
            continue
        upstream_type = upstream_def.get_port_type(edge.src_port, is_input=False)
        if not isinstance(upstream_type, str):
            continue
        if is_flow_type_name(upstream_type):
            # 流程类型不参与数据端口类型推断
            continue
        if not is_generic_type_name(upstream_type):
            non_generic_inputs.append(upstream_type)
    
    if len(non_generic_inputs) > 0:
        pick = list(dict.fromkeys(non_generic_inputs))[0]
        if is_list_like and (pick in BASE_TO_LIST_MAP):
            mapped2 = BASE_TO_LIST_MAP.get(pick, pick)
            if not is_generic_type_name(mapped2):
                return mapped2
        if not is_generic_type_name(pick):
            return pick
    
    return None


def infer_input_type_from_edges(
    port_name: str,
    node_model: NodeModel,
    graph_model: GraphModel,
    executor,
    log_callback=None,
    edge_lookup: EdgeLookup | None = None,
) -> Optional[str]:
    """从入边推断输入端口类型。
    
    当源端口为泛型家族时，尝试通用派生为具体类型。
    
    Args:
        port_name: 端口名称
        node_model: 当前节点模型
        graph_model: 图模型
        executor: 执行器实例
        log_callback: 日志回调
    
    Returns:
        推断出的类型，失败返回None
    """
    if not isinstance(port_name, str) or port_name == "":
        return None
    
    candidate_types: List[str] = []
    
    incoming_edges = _iter_incoming_edges(node_model.id, port_name, graph_model, edge_lookup)
    for edge in incoming_edges:
        source = graph_model.nodes.get(edge.src_node)
        if source is None:
            continue

        source_def = executor._get_node_def_for_model(source)
        if source_def is None:
            continue

        source_type = source_def.get_port_type(edge.src_port, is_input=False)
        if isinstance(source_type, str):
            if is_flow_type_name(source_type):
                # 流程端口不参与数据端口类型推断
                continue
            if not is_generic_type_name(source_type):
                candidate_types.append(source_type)
            else:
                # 源端为"泛型家族" → 尝试通用派生为具体类型
                derived = derive_concrete_type_from_source_node(
                    source,
                    source_def,
                    edge.src_port,
                    graph_model,
                    executor,
                    edge_lookup=edge_lookup,
                )
                if isinstance(derived, str) and (not is_generic_type_name(derived)) and (not is_flow_type_name(derived)):
                    candidate_types.append(derived)
    
    if len(candidate_types) == 0:
        return None
    
    unique_types = list(dict.fromkeys(candidate_types))
    if len(unique_types) > 1 and executor is not None:
        executor._log(f"[端口类型] 输入类型推断出现多种候选 {unique_types}，将使用首个 '{unique_types[0]}'", log_callback)
    
    return unique_types[0]


def infer_output_type_from_edges(
    port_name: str,
    node_model: NodeModel,
    graph_model: GraphModel,
    executor,
    log_callback=None,
    edge_lookup: EdgeLookup | None = None,
) -> Optional[str]:
    """从出边推断输出端口类型。

    当前策略：直接基于出边目标端口的显式类型进行收敛。

    Args:
        port_name: 端口名称
        node_model: 当前节点模型
        graph_model: 图模型
        executor: 执行器实例
        log_callback: 日志回调

    Returns:
        推断出的类型，失败返回None
    """
    if not isinstance(port_name, str) or port_name == "":
        return None

    outgoing_edges = _iter_outgoing_edges(node_model.id, port_name, graph_model, edge_lookup)

    # 基于出边目标端口的显式类型
    types: List[str] = []
    for edge in outgoing_edges:
        dest = graph_model.nodes.get(edge.dst_node)
        if dest is None:
            continue

        dest_def = executor._get_node_def_for_model(dest)
        if dest_def is None:
            continue

        dest_type = dest_def.get_port_type(edge.dst_port, is_input=True)
        if not isinstance(dest_type, str):
            continue
        if is_flow_type_name(dest_type):
            # 仅为数据端口推断类型，忽略流程端口
            continue
        if not is_generic_type_name(dest_type):
            types.append(dest_type)
    
    if len(types) == 0:
        return None
    
    unique_types = list(dict.fromkeys(types))
    if len(unique_types) > 1 and executor is not None:
        executor._log(f"[端口类型] 输出类型推断出现多种候选 {unique_types}，将使用首个 '{unique_types[0]}'", log_callback)
    
    return unique_types[0]


def infer_output_type_from_self_inputs(
    node_model: NodeModel,
    node_def,
    declared_output_type: str,
    executor,
    log_callback=None
) -> Optional[str]:
    """基于本节点输入常量派生输出类型。
    
    当输出声明为列表类/泛型列表，尝试从输入常量的"基础标量类型"派生为"X列表"。
    当输出声明为泛型（非列表），尝试直接采用输入常量推断出的基础标量类型。
    
    Args:
        node_model: 节点模型
        node_def: 节点定义
        declared_output_type: 输出端口声明的类型
        executor: 执行器实例
        log_callback: 日志回调
    
    Returns:
        派生出的类型，失败返回None
    """
    if node_def is None:
        return None

    # 仅基于“真实输入端口”的常量参与类型推断，忽略纯参数面板配置项
    # （如“数据类型转换”的“目标类型”等，这些并不存在对应的端口）
    valid_input_port_names: List[str] = []
    inputs_attr = getattr(node_model, "inputs", None)
    if isinstance(inputs_attr, list) and len(inputs_attr) > 0:
        valid_input_port_names = [
            getattr(p, "name", "")
            for p in inputs_attr
            if hasattr(p, "name") and isinstance(getattr(p, "name", ""), str)
        ]
        valid_input_port_names = [name for name in valid_input_port_names if name != ""]

    candidates: List[str] = []
    input_constants = dict(getattr(node_model, "input_constants", {}) or {})
    
    if not input_constants:
        return None
    
    is_output_list_like = False
    if isinstance(declared_output_type, str):
        text = declared_output_type.strip()
        is_output_list_like = ("列表" in text) or (text == "泛型列表")
    
    # 遍历所有有常量值的输入端口，仅在输入端口自身为"泛型家族/未声明/动态"的场景下参与派生
    for input_port_name, value_text in input_constants.items():
        # 若常量键不是节点的真实输入端口名（例如仅存在于参数面板），则跳过
        if valid_input_port_names and input_port_name not in valid_input_port_names:
            continue

        port_decl_type = node_def.get_port_type(input_port_name, is_input=True)
        if not is_generic_type_name(port_decl_type):
            # 已是具体类型的输入端口，不参与"从常量推断输出"以避免错误放大
            continue
        
        scalar_type = infer_type_from_value(str(value_text))
        if not isinstance(scalar_type, str) or scalar_type.strip() == "":
            continue
        
        if is_output_list_like:
            mapped = BASE_TO_LIST_MAP.get(scalar_type, scalar_type)
            if not is_generic_type_name(mapped):
                candidates.append(mapped)
        else:
            if not is_generic_type_name(scalar_type):
                candidates.append(scalar_type)
    
    if len(candidates) == 0:
        return None
    
    unique_types = list(dict.fromkeys(candidates))
    if len(unique_types) > 1 and executor is not None:
        executor._log(f"[端口类型] 输出类型（基于本节点入参常量）出现多种候选 {unique_types}，将使用首个 '{unique_types[0]}'", log_callback)
    
    return unique_types[0]


def infer_dict_key_value_types_for_input(
    node_model: NodeModel,
    port_name: str,
    graph_model: GraphModel,
    executor,
    log_callback=None,
    edge_lookup: EdgeLookup | None = None,
) -> Optional[Tuple[str, str]]:
    """为输入端口推断字典键/值类型。

    当前策略：
    - 遍历指向该端口的所有入边；
    - 若上游端口的最终类型为“别名字典”（如“字符串_GUID列表字典”），
      则按别名解析出键/值类型并参与候选集合；
    - 多个来源给出不同键/值组合时，记录日志并优先取首个组合。
    """
    if not isinstance(port_name, str) or port_name == "":
        return None

    incoming_edges = _iter_incoming_edges(node_model.id, port_name, graph_model, edge_lookup)
    if not incoming_edges:
        return None

    candidates: List[Tuple[str, str]] = []

    # 别名字典路径：上游端口类型为“X_Y字典”/“X-Y字典”等别名时，从类型名中解析键/值类型
    port_type_overrides: Dict[str, Dict[str, str]] = build_port_type_overrides(graph_model)

    for edge in incoming_edges:
        src_node = graph_model.nodes.get(edge.src_node)
        if src_node is None:
            continue

        # 优先：使用 GraphModel.metadata.port_type_overrides 中的最终类型
        alias_type: str = ""
        node_overrides = get_node_port_type_overrides_for_id(port_type_overrides, src_node.id)
        if isinstance(node_overrides, dict):
            override_raw = node_overrides.get(edge.src_port)
            if isinstance(override_raw, str):
                alias_type = override_raw.strip()

        # 回退：从节点定义的输出端口类型中获取
        if not alias_type and executor is not None:
            src_def = executor._get_node_def_for_model(src_node)
            if src_def is not None:
                type_raw = src_def.get_port_type(edge.src_port, is_input=False)
                if isinstance(type_raw, str):
                    alias_type = type_raw.strip()

        ok, key_type, value_type = parse_typed_dict_alias(alias_type)
        if ok:
            candidates.append((key_type, value_type))

    if len(candidates) == 0:
        return None

    # 去重保持顺序
    unique_candidates: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for key_type, value_type in candidates:
        pair = (key_type, value_type)
        if pair in seen:
            continue
        seen.add(pair)
        unique_candidates.append(pair)

    if len(unique_candidates) > 1 and executor is not None:
        executor._log(
            f"[端口类型/字典] 键/值类型推断出现多种候选 {unique_candidates}，将使用首个 {unique_candidates[0]}",
            log_callback,
        )

    return unique_candidates[0]

