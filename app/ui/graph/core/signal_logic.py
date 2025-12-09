from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence

from engine.graph.common import (
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_LISTEN_STATIC_OUTPUTS,
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
)
from engine.graph.models.graph_model import NodeModel
from engine.graph.models.package_model import SignalConfig
from engine.nodes.node_definition_loader import NodeDef


@dataclass(frozen=True)
class SignalBindingContext:
    """信号绑定上下文（纯数据）"""

    signal_config: SignalConfig
    bound_signal_id: str


@dataclass(frozen=True)
class SignalPortSyncPlan:
    """信号节点端口与常量的同步计划"""

    bound_signal_id: str
    signal_name_constant: Optional[str]
    add_inputs: List[str]
    add_outputs: List[str]


def _extract_param_type_map(signal_config: SignalConfig) -> Dict[str, str]:
    parameters = getattr(signal_config, "parameters", []) or []
    param_type_map: Dict[str, str] = {}
    for parameter_config in parameters:
        param_name = getattr(parameter_config, "name", "")
        param_type = getattr(parameter_config, "parameter_type", "")
        if param_name and param_type:
            param_type_map[str(param_name)] = str(param_type)
    return param_type_map


def _infer_signal_config_from_constants(
    input_constants: Mapping[str, object],
    signals_dict: Mapping[str, SignalConfig],
) -> Optional[SignalConfig]:
    """基于节点上的“信号名”输入常量，从信号字典推断 SignalConfig。"""
    if not isinstance(signals_dict, Mapping):
        return None
    raw_value = input_constants.get(SIGNAL_NAME_PORT_NAME) if isinstance(input_constants, Mapping) else None
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None

    for candidate in signals_dict.values():
        signal_name_value = getattr(candidate, "signal_name", None)
        if str(signal_name_value or "").strip() == text:
            return candidate
    return None


def resolve_signal_binding(
    node: NodeModel,
    signals_dict: Mapping[str, SignalConfig],
    bound_signal_id: Optional[str],
) -> Optional[SignalBindingContext]:
    """根据绑定 ID 或“信号名”常量获取有效的信号配置上下文。"""
    node_title = getattr(node, "title", "") or ""
    if node_title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
        return None

    if bound_signal_id:
        config = signals_dict.get(bound_signal_id)
        if config is not None:
            return SignalBindingContext(signal_config=config, bound_signal_id=str(bound_signal_id))

    config = _infer_signal_config_from_constants(getattr(node, "input_constants", {}) or {}, signals_dict)
    if config is None:
        return None

    inferred_id = getattr(config, "signal_id", "") or ""
    if not inferred_id:
        return None

    return SignalBindingContext(signal_config=config, bound_signal_id=str(inferred_id))


def build_signal_node_def_proxy(
    node_title: str,
    base_def: NodeDef,
    context: SignalBindingContext,
) -> Optional[NodeDef]:
    """基于当前信号绑定构造带参数类型的 NodeDef 代理。"""
    param_type_map = _extract_param_type_map(context.signal_config)
    if not param_type_map:
        return None

    input_types: Dict[str, str] = dict(getattr(base_def, "input_types", {}) or {})
    output_types: Dict[str, str] = dict(getattr(base_def, "output_types", {}) or {})

    if node_title == SIGNAL_SEND_NODE_TITLE:
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
        for param_name, param_type in param_type_map.items():
            if param_name in static_inputs:
                continue
            input_types[param_name] = param_type
    elif node_title == SIGNAL_LISTEN_NODE_TITLE:
        static_outputs = set(SIGNAL_LISTEN_STATIC_OUTPUTS)
        for param_name, param_type in param_type_map.items():
            if param_name in static_outputs:
                continue
            output_types[param_name] = param_type
    else:
        return None

    return NodeDef(
        name=base_def.name,
        category=base_def.category,
        inputs=list(base_def.inputs),
        outputs=list(base_def.outputs),
        description=base_def.description,
        scopes=list(base_def.scopes),
        mount_restrictions=list(base_def.mount_restrictions),
        doc_reference=base_def.doc_reference,
        input_types=input_types,
        output_types=output_types,
        input_generic_constraints=dict(base_def.input_generic_constraints),
        output_generic_constraints=dict(base_def.output_generic_constraints),
        dynamic_port_type=base_def.dynamic_port_type,
        is_composite=base_def.is_composite,
        composite_id=base_def.composite_id,
    )


def plan_signal_port_sync(node: NodeModel, context: SignalBindingContext) -> SignalPortSyncPlan:
    """根据信号定义生成端口与常量更新计划（纯数据，不落地 UI）。"""
    node_title = getattr(node, "title", "") or ""
    existing_inputs = {getattr(port, "name", "") for port in (node.inputs or []) if getattr(port, "name", "")}
    existing_outputs = {getattr(port, "name", "") for port in (node.outputs or []) if getattr(port, "name", "")}

    add_inputs: List[str] = []
    add_outputs: List[str] = []

    parameters: Sequence = getattr(context.signal_config, "parameters", []) or []
    parameter_names = [getattr(param, "name", "") for param in parameters if getattr(param, "name", "")]

    signal_name_constant = getattr(context.signal_config, "signal_name", "") or None

    if node_title == SIGNAL_SEND_NODE_TITLE:
        static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
        for param_name in parameter_names:
            if param_name in static_inputs or param_name in existing_inputs:
                continue
            add_inputs.append(param_name)
    elif node_title == SIGNAL_LISTEN_NODE_TITLE:
        if SIGNAL_NAME_PORT_NAME not in existing_inputs:
            add_inputs.append(SIGNAL_NAME_PORT_NAME)
        static_outputs = set(SIGNAL_LISTEN_STATIC_OUTPUTS)
        for param_name in parameter_names:
            if param_name in static_outputs or param_name in existing_outputs:
                continue
            add_outputs.append(param_name)
    else:
        return SignalPortSyncPlan(
            bound_signal_id=context.bound_signal_id,
            signal_name_constant=signal_name_constant,
            add_inputs=[],
            add_outputs=[],
        )

    return SignalPortSyncPlan(
        bound_signal_id=context.bound_signal_id,
        signal_name_constant=signal_name_constant,
        add_inputs=add_inputs,
        add_outputs=add_outputs,
    )


__all__ = [
    "SignalBindingContext",
    "SignalPortSyncPlan",
    "build_signal_node_def_proxy",
    "plan_signal_port_sync",
    "resolve_signal_binding",
]

