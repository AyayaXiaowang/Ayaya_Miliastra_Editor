from __future__ import annotations

import keyword
from typing import Dict, List, Mapping, Sequence, Tuple

from engine.graph.common import format_constant
from engine.graph.models import NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.port_type_system import is_flow_port_with_context

from engine.graph.reverse_codegen._common import ReverseGraphCodeError

DYNAMIC_NUMERIC_PORT_START_INDEX: int = 0


def _is_keyword_arg_name(name: str) -> bool:
    """判断端口名是否可作为 Python 关键字参数名。"""
    return bool(name) and name.isidentifier() and (not keyword.iskeyword(name))


def _collect_provided_input_args(
    *,
    node: NodeModel,
    node_library: Dict[str, NodeDef],
    data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
    var_mapping: Mapping[Tuple[str, str], str],
) -> List[Tuple[str, str]]:
    """收集节点输入端口中需要输出为调用入参的 (port_name, expr) 列表。"""
    provided: List[Tuple[str, str]] = []
    for port in (node.inputs or []):
        port_name = str(getattr(port, "name", "") or "")
        if not port_name:
            continue
        if is_flow_port_with_context(node, port_name, False, node_library):
            continue

        source = data_in_edge.get((node.id, port_name))
        if source is not None:
            expr = var_mapping.get((source[0], source[1]))
            if expr is None:
                raise ReverseGraphCodeError(
                    f"无法解析数据来源变量：{node.title}.{port_name} 来自 {source}"
                )
            provided.append((port_name, expr))
            continue

        if port_name in (node.input_constants or {}):
            provided.append((port_name, format_constant((node.input_constants or {}).get(port_name))))

    return provided


def _render_keyword_args_only(*, provided: Sequence[Tuple[str, str]], inputs_in_order: Sequence[str]) -> List[str]:
    """以关键字参数形式渲染调用入参列表。"""
    provided_map = {k: v for k, v in provided}
    keyword_args: List[str] = []

    for port_name in inputs_in_order:
        if port_name in provided_map:
            keyword_args.append(f"{port_name}={provided_map[port_name]}")

    # 对于动态输入端口（不在 NodeDef.inputs 中），按 node.inputs 顺序追加（稳定）
    for port_name, expr in provided:
        if port_name in inputs_in_order:
            continue
        keyword_args.append(f"{port_name}={expr}")

    return keyword_args


def _is_numeric_dynamic_ports(names: Sequence[str]) -> bool:
    """判断不可关键字端口名是否属于“动态数字端口”集合。"""
    if not names:
        return False
    return all(str(name).isdigit() for name in names)


def _render_positional_for_numeric_dynamic_ports(
    *,
    node_title: str,
    provided: Sequence[Tuple[str, str]],
    inputs_in_order: Sequence[str],
) -> List[str]:
    """对动态数字端口按位置参数渲染并在尾部追加可关键字参数。"""
    provided_map = {k: v for k, v in provided}
    non_kw_names = [name for name in provided_map.keys() if not _is_keyword_arg_name(str(name))]
    numeric_ports = sorted({int(str(name)) for name in non_kw_names})

    if numeric_ports and numeric_ports[0] != DYNAMIC_NUMERIC_PORT_START_INDEX:
        raise ReverseGraphCodeError(
            f"节点 {node_title} 的数字端口必须从 0 开始连续提供，但当前最小端口为 {numeric_ports[0]}"
        )

    positional_args: List[str] = []
    keyword_args: List[str] = []
    last_index = numeric_ports[-1] if numeric_ports else -1
    for expected in range(DYNAMIC_NUMERIC_PORT_START_INDEX, last_index + 1):
        key = str(expected)
        if key not in provided_map:
            raise ReverseGraphCodeError(
                f"节点 {node_title} 的数字端口必须连续提供（缺少 {key!r}），无法生成位置参数"
            )
        positional_args.append(provided_map[key])

    # 其余（可关键字）端口按 NodeDef.inputs 顺序追加为 keyword，避免跳位
    for port_name in inputs_in_order:
        if port_name in provided_map and _is_keyword_arg_name(port_name):
            keyword_args.append(f"{port_name}={provided_map[port_name]}")

    for port_name, expr in provided:
        if port_name in inputs_in_order or port_name.isdigit():
            continue
        if not _is_keyword_arg_name(port_name):
            raise ReverseGraphCodeError(f"节点 {node_title} 的动态端口名不可作为关键字参数：{port_name!r}")
        keyword_args.append(f"{port_name}={expr}")

    return positional_args + keyword_args


def _render_positional_for_static_non_keyword_ports(
    *,
    node_title: str,
    provided: Sequence[Tuple[str, str]],
    inputs_in_order: Sequence[str],
) -> List[str]:
    """对静态端口中的不可关键字名称尝试用位置参数表达并追加其余关键字参数。"""
    provided_map = {k: v for k, v in provided}
    max_index = -1
    for idx, name in enumerate(inputs_in_order):
        if name in provided_map and (not _is_keyword_arg_name(name)):
            max_index = max(max_index, idx)
    if max_index < 0:
        raise ReverseGraphCodeError(
            f"节点 {node_title} 存在不可关键字参数的动态端口，且无法按位置参数表达"
        )

    positional_args: List[str] = []
    keyword_args: List[str] = []

    for idx in range(0, max_index + 1):
        port_name = inputs_in_order[idx]
        if port_name not in provided_map:
            raise ReverseGraphCodeError(
                f"节点 {node_title} 需要以位置参数表达端口 {inputs_in_order[max_index]!r}，"
                f"但其前置端口 {port_name!r} 缺少数据来源/常量，无法不跳位生成"
            )
        positional_args.append(provided_map[port_name])

    for port_name in inputs_in_order[max_index + 1 :]:
        if port_name in provided_map:
            keyword_args.append(f"{port_name}={provided_map[port_name]}")

    for port_name, expr in provided:
        if port_name in inputs_in_order:
            continue
        if not _is_keyword_arg_name(port_name):
            raise ReverseGraphCodeError(f"节点 {node_title} 的动态端口名不可作为关键字参数：{port_name!r}")
        keyword_args.append(f"{port_name}={expr}")

    return positional_args + keyword_args


def _render_node_call_args(
    *,
    node: NodeModel,
    node_def: NodeDef,
    node_library: Dict[str, NodeDef],
    data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
    var_mapping: Mapping[Tuple[str, str], str],
) -> List[str]:
    """渲染节点调用参数（不包含 self.game）。"""
    provided = _collect_provided_input_args(
        node=node,
        node_library=node_library,
        data_in_edge=data_in_edge,
        var_mapping=var_mapping,
    )
    if not provided:
        return []

    inputs_in_order = [str(x) for x in list(getattr(node_def, "inputs", []) or [])]
    provided_map = {k: v for k, v in provided}

    # 参数输出策略：
    # - 优先关键字参数（可读、避免跳位）；
    # - 若端口名不可作为 keyword，则尝试用位置参数（要求“从0开始连续提供”）。
    needs_positional = any((not _is_keyword_arg_name(str(name))) for name in provided_map.keys())
    if not needs_positional:
        return _render_keyword_args_only(provided=provided, inputs_in_order=inputs_in_order)

    non_kw_names = [str(name) for name in provided_map.keys() if not _is_keyword_arg_name(str(name))]
    if _is_numeric_dynamic_ports(non_kw_names):
        return _render_positional_for_numeric_dynamic_ports(
            node_title=str(getattr(node, "title", "") or ""),
            provided=provided,
            inputs_in_order=inputs_in_order,
        )

    return _render_positional_for_static_non_keyword_ports(
        node_title=str(getattr(node, "title", "") or ""),
        provided=provided,
        inputs_in_order=inputs_in_order,
    )

