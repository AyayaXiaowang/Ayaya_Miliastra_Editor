# -*- coding: utf-8 -*-
"""
port_type_generics: 泛型家族与通用端口类型推断工具。

职责：
- 在不抛出异常的前提下，从节点定义中读取端口声明类型；
- 当端口声明为“泛型家族”时，基于输入常量与上游连线派生具体类型；
- 基于入/出边与动态端口规则推断输入/输出端口的数据类型；
- 结合 GraphModel.metadata 中的 port_type_overrides 作为最高优先级覆盖。

模块定位：
- 作为 `app.automation.ports` 包的内部实现模块，仅供本包内部使用；
- 包外调用方如需使用端口类型推断相关工具，应通过
  `app.automation.ports.port_type_inference` 导入公共推断函数（例如
  `safe_get_port_type_from_node_def`、`infer_input_type_from_edges` 等），避免直接
  依赖本模块，以便未来在不破坏入口层 API 的前提下自由重构内部实现。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.automation.ports._type_utils import infer_type_from_value
from app.automation.ports.port_type_common import (
    get_non_empty_str,
    is_generic_type_name,
    is_flow_type_name,
    is_list_like_type_name,
    pick_first_unique,
    unique_preserve_order,
    upgrade_to_list_type,
)
from app.automation.ports.port_type_context import (
    EdgeLookup,
    build_port_type_overrides,
    resolve_port_type_with_overrides,
    _iter_incoming_edges,
    _iter_outgoing_edges,
)
from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.nodes.port_name_rules import get_dynamic_port_type
from engine.nodes.port_type_system import FLOW_PORT_TYPE
from engine.utils.graph.graph_utils import is_flow_port_name


def safe_get_port_type_from_node_def(
    node_def: Any,
    port_name: str,
    is_input: bool,
) -> str:
    """在不抛出异常的前提下获取端口类型。

    规则基本与 `NodeDef.get_port_type` 保持一致，但在端口缺少类型定义时返回空字符串：
    - 优先读取显式 `input_types` / `output_types`；
    - 再根据动态端口规则 `get_dynamic_port_type` 推断；
    - 对流程端口统一返回 `FLOW_PORT_TYPE`；
    - 其余情况返回 ""，由调用方决定如何回退。
    """
    if node_def is None:
        return ""

    if not isinstance(port_name, str) or str(port_name).strip() == "":
        return ""

    type_mapping: Dict[str, Any] = {}
    if is_input:
        type_mapping = getattr(node_def, "input_types", {}) or {}
    else:
        type_mapping = getattr(node_def, "output_types", {}) or {}

    if isinstance(type_mapping, dict) and port_name in type_mapping:
        raw_type = type_mapping.get(port_name, "")
        if raw_type is None:
            return ""
        text = str(raw_type)
        return text

    dynamic_type = get_dynamic_port_type(
        str(port_name),
        type_mapping,
        getattr(node_def, "dynamic_port_type", ""),
    )
    dynamic_text = get_non_empty_str(dynamic_type)
    if dynamic_text:
        return dynamic_text

    if is_flow_port_name(str(port_name)):
        return FLOW_PORT_TYPE

    return ""


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

    尝试基于“源节点的输入常量”和“上游非泛型入边”推断具体类型。
    """
    if source_node is None or source_node_def is None or not isinstance(source_port_name, str):
        return None

    # 0) 优先：若 GraphModel.metadata 中存在端口类型覆盖信息，则直接采用
    overrides = build_port_type_overrides(graph_model)
    source_node_id = getattr(source_node, "id", "")
    override_type = resolve_port_type_with_overrides(
        overrides_mapping=overrides,
        node_identifier=source_node_id,
        port_name=source_port_name,
    )
    if isinstance(override_type, str):
        return override_type

    declared_output = safe_get_port_type_from_node_def(
        source_node_def,
        source_port_name,
        is_input=False,
    )
    is_list_like = is_list_like_type_name(declared_output)

    # 1) 先看源节点的输入常量
    constants_map = dict(getattr(source_node, "input_constants", {}) or {})
    if constants_map:
        scalar_candidates: List[str] = []
        for input_name, value in constants_map.items():
            base = infer_type_from_value(str(value))
            base_text = get_non_empty_str(base)
            if base_text and not is_generic_type_name(base_text):
                scalar_candidates.append(base_text)

        if len(scalar_candidates) > 0:
            base_pick = pick_first_unique(scalar_candidates)
            if base_pick is None:
                return None
            if is_list_like:
                upgraded_type = upgrade_to_list_type(declared_output, base_pick)
                upgraded_text = get_non_empty_str(upgraded_type)
                # 仅在确实从基础标量提升为列表类型且结果非泛型时才返回
                if (
                    upgraded_text
                    and upgraded_text != get_non_empty_str(base_pick)
                    and not is_generic_type_name(upgraded_text)
                ):
                    return upgraded_text
            else:
                if not is_generic_type_name(base_pick):
                    return base_pick

    # 2) 若无常量或未得出，尝试基于“源节点的入边源端口类型”做一次收敛（仅取非泛型候选）
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
        upstream_def = executor.get_node_def_for_model(upstream_node)
        if upstream_def is None:
            continue
        upstream_type = safe_get_port_type_from_node_def(
            upstream_def,
            edge.src_port,
            is_input=False,
        )
        upstream_text = get_non_empty_str(upstream_type)
        if upstream_text == "":
            continue
        if is_flow_type_name(upstream_text):
            # 流程类型不参与数据端口类型推断
            continue
        if not is_generic_type_name(upstream_text):
            non_generic_inputs.append(upstream_text)

    if len(non_generic_inputs) > 0:
        pick = pick_first_unique(non_generic_inputs)
        if pick is None:
            return None
        if is_list_like:
            upgraded_type = upgrade_to_list_type(declared_output, pick)
            upgraded_text = get_non_empty_str(upgraded_type)
            if (
                upgraded_text
                and upgraded_text != get_non_empty_str(pick)
                and not is_generic_type_name(upgraded_text)
            ):
                return upgraded_text
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
    """
    if not isinstance(port_name, str) or port_name == "":
        return None

    candidate_types: List[str] = []

    incoming_edges = _iter_incoming_edges(node_model.id, port_name, graph_model, edge_lookup)
    for edge in incoming_edges:
        source = graph_model.nodes.get(edge.src_node)
        if source is None:
            continue

        source_def = executor.get_node_def_for_model(source)
        if source_def is None:
            continue

        source_type = safe_get_port_type_from_node_def(
            source_def,
            edge.src_port,
            is_input=False,
        )
        source_text = get_non_empty_str(source_type)
        if source_text == "":
            if executor is not None:
                source_title = getattr(source, "title", "") or ""
                source_identifier = getattr(source, "id", "") or ""
                executor.log(
                    f"[端口类型] 源节点 '{source_title}'({source_identifier}) 的输出端口 '{edge.src_port}' 缺少类型定义，在输入类型推断时已忽略该入边",
                    log_callback,
                )
            continue
        if is_flow_type_name(source_text):
            # 流程端口不参与数据端口类型推断
            continue
        if not is_generic_type_name(source_text):
            candidate_types.append(source_text)
        else:
            # 源端为“泛型家族” → 尝试通用派生为具体类型
            derived = derive_concrete_type_from_source_node(
                source,
                source_def,
                edge.src_port,
                graph_model,
                executor,
                edge_lookup=edge_lookup,
            )
            derived_text = get_non_empty_str(derived)
            if derived_text and (not is_generic_type_name(derived_text)) and (not is_flow_type_name(derived_text)):
                candidate_types.append(derived_text)

    if len(candidate_types) == 0:
        return None

    unique_types = unique_preserve_order(candidate_types)
    if len(unique_types) > 1 and executor is not None:
        executor.log(f"[端口类型] 输入类型推断出现多种候选 {unique_types}，将使用首个 '{unique_types[0]}'", log_callback)

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

        dest_def = executor.get_node_def_for_model(dest)
        if dest_def is None:
            continue

        dest_type = safe_get_port_type_from_node_def(
            dest_def,
            edge.dst_port,
            is_input=True,
        )
        dest_text = get_non_empty_str(dest_type)
        if dest_text == "":
            if executor is not None:
                dest_title = getattr(dest, "title", "") or ""
                dest_identifier = getattr(dest, "id", "") or ""
                executor.log(
                    f"[端口类型] 目标节点 '{dest_title}'({dest_identifier}) 的输入端口 '{edge.dst_port}' 缺少类型定义，在输出类型推断时已忽略该出边",
                    log_callback,
                )
            continue
        if is_flow_type_name(dest_text):
            # 仅为数据端口推断类型，忽略流程端口
            continue
        if not is_generic_type_name(dest_text):
            types.append(dest_text)

    if len(types) == 0:
        return None

    unique_types = unique_preserve_order(types)
    if len(unique_types) > 1 and executor is not None:
        executor.log(f"[端口类型] 输出类型推断出现多种候选 {unique_types}，将使用首个 '{unique_types[0]}'", log_callback)

    return unique_types[0]


def infer_output_type_from_self_inputs(
    node_model: NodeModel,
    node_def,
    declared_output_type: str,
    executor,
    log_callback=None,
) -> Optional[str]:
    """基于本节点输入常量派生输出类型。

    当输出声明为列表类/泛型列表，尝试从输入常量的“基础标量类型”派生为“X列表”。
    当输出声明为泛型（非列表），尝试直接采用输入常量推断出的基础标量类型。
    """
    if node_def is None:
        return None

    # 仅基于“真实输入端口”的常量参与类型推断，忽略纯参数面板配置项
    # （如“数据类型转换”的“目标类型”等，这些并不存在对应的端口）
    valid_input_port_names: List[str] = []
    inputs_attr = getattr(node_model, "inputs", None)
    if isinstance(inputs_attr, list) and len(inputs_attr) > 0:
        valid_input_port_names = [
            getattr(port_object, "name", "")
            for port_object in inputs_attr
            if hasattr(port_object, "name") and isinstance(getattr(port_object, "name", ""), str)
        ]
        valid_input_port_names = [name for name in valid_input_port_names if name != ""]

    candidates: List[str] = []
    input_constants = dict(getattr(node_model, "input_constants", {}) or {})

    if not input_constants:
        return None

    is_output_list_like = is_list_like_type_name(declared_output_type)

    # 遍历所有有常量值的输入端口，仅在输入端口自身为“泛型家族/未声明/动态”场景下参与派生
    for input_port_name, value_text in input_constants.items():
        # 若常量键不是节点的真实输入端口名（例如仅存在于参数面板），则跳过
        if valid_input_port_names and input_port_name not in valid_input_port_names:
            continue

        port_decl_type = safe_get_port_type_from_node_def(
            node_def,
            input_port_name,
            is_input=True,
        )
        # 当端口已声明为具体非泛型类型时，不参与“从常量推断输出”以避免错误放大。
        # 对于缺少声明的端口（空字符串），视为可参与派生。
        port_decl_text = get_non_empty_str(port_decl_type)
        if port_decl_text and not is_generic_type_name(port_decl_text):
            # 已是具体类型的输入端口，不参与“从常量推断输出”以避免错误放大
            continue

        scalar_type = infer_type_from_value(str(value_text))
        scalar_text = get_non_empty_str(scalar_type)
        if scalar_text == "":
            continue

        if is_output_list_like:
            upgraded_type = upgrade_to_list_type(declared_output_type, scalar_type)
            upgraded_text = get_non_empty_str(upgraded_type)
            if (
                upgraded_text
                and upgraded_text != scalar_text
                and not is_generic_type_name(upgraded_text)
            ):
                candidates.append(upgraded_text)
        else:
            if not is_generic_type_name(scalar_text):
                candidates.append(scalar_text)

    if len(candidates) == 0:
        return None

    unique_types = unique_preserve_order(candidates)
    if len(unique_types) > 1 and executor is not None:
        executor.log(
            f"[端口类型] 输出类型（基于本节点入参常量）出现多种候选 {unique_types}，将使用首个 '{unique_types[0]}'",
            log_callback,
        )

    return unique_types[0]


__all__ = [
    "safe_get_port_type_from_node_def",
    "derive_concrete_type_from_source_node",
    "infer_input_type_from_edges",
    "infer_output_type_from_edges",
    "infer_output_type_from_self_inputs",
]


