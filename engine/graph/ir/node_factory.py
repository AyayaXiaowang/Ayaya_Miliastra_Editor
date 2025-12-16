from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Iterator, Mapping

from engine.graph.models import NodeModel, PortModel, EdgeModel
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.nodes.node_definition_loader import NodeDef
from .var_env import VarEnv
from .validators import Validators
from .edge_router import create_data_edges_for_node_enhanced
from .arg_normalizer import normalize_call_arguments, is_reserved_argument


@dataclass
class FactoryContext:
    node_library: Dict[str, NodeDef]
    node_name_index: Dict[str, str]
    verbose: bool = False
    # 结构体/信号等语义推导所需的“只读索引”，由上层编排器按需填充。
    struct_name_to_id: Optional[Dict[str, str]] = None
    struct_fields_by_id: Optional[Dict[str, List[str]]] = None
    signal_repo: Optional[Any] = None  # SignalRepository-like


def create_event_node(event_name: str, method: ast.FunctionDef, ctx: FactoryContext) -> NodeModel:
    full_key = ctx.node_name_index.get(event_name)
    node_def = ctx.node_library.get(full_key) if full_key else None

    node_id = f"event_{event_name}_{uuid.uuid4().hex[:8]}"

    input_ports: List[PortModel] = []
    # 若事件名在节点库中有定义（例如【监听信号】这类带输入端口的事件节点），
    # 则补齐输入端口，保证 UI 中能够正确显示并编辑对应选择端口（如“信号名”）。
    if node_def is not None:
        for pname in getattr(node_def, "inputs", []) or []:
            if isinstance(pname, str) and pname and "~" not in pname:
                input_ports.append(PortModel(name=pname, is_input=True))

    output_ports: List[PortModel] = []
    # 流程出
    output_ports.append(PortModel(name="流程出", is_input=False))
    # 数据输出：方法参数（跳过 self）
    for arg in method.args.args[1:]:
        output_ports.append(PortModel(name=arg.arg, is_input=False))

    node = NodeModel(
        id=node_id,
        title=event_name,
        category="事件节点",
        pos=(100.0, 100.0),
        inputs=input_ports,
        outputs=output_ports,
    )
    # 源码行号：用于 UI 定位与错误提示（事件节点对应 handler 方法定义范围）
    node.source_lineno = getattr(method, "lineno", 0) or 0
    node.source_end_lineno = getattr(method, "end_lineno", node.source_lineno) or node.source_lineno
    return node


def register_event_outputs(event_node: NodeModel, method: ast.FunctionDef, env: VarEnv) -> None:
    for i, arg in enumerate(method.args.args[1:]):  # 跳过 self
        port_index = i + 1  # 0 是流程出
        if len(event_node.outputs) > port_index:
            env.set_variable(arg.arg, event_node.id, event_node.outputs[port_index].name)


def _resolve_local_constant(expr: ast.AST, env: Optional[VarEnv]) -> Any:
    """在 extract_constant_value 无法静态提取时，补充解析“方法体内命名常量”。

    约定：
    - 仅支持 `变量名`（ast.Name）引用；
    - 值来源于 `VarEnv.local_const_values`（由 flow_builder 在解析方法体前预扫描得到）。
    """
    if env is None:
        return NOT_EXTRACTABLE
    if not isinstance(expr, ast.Name):
        return NOT_EXTRACTABLE
    name_text = str(expr.id or "").strip()
    if not name_text:
        return NOT_EXTRACTABLE
    if env.has_local_constant(name_text):
        return env.get_local_constant(name_text)
    return NOT_EXTRACTABLE


def _extract_constant_value_with_env(expr: ast.AST, env: Optional[VarEnv]) -> Any:
    value = extract_constant_value(expr)  # type: ignore[arg-type]
    if value is not NOT_EXTRACTABLE:
        return value
    return _resolve_local_constant(expr, env)


def create_node_from_call(
    call_node: ast.Call,
    ctx: FactoryContext,
    validators: Validators,
    *,
    env: Optional[VarEnv] = None,
) -> Optional[NodeModel]:
    if isinstance(call_node.func, ast.Name):
        func_name = call_node.func.id
    elif isinstance(call_node.func, ast.Attribute):
        func_name = call_node.func.attr
    else:
        return None

    full_key = ctx.node_name_index.get(func_name)
    node_def = ctx.node_library.get(full_key) if full_key else None
    if not node_def:
        if ctx.verbose:
            pass
        return None

    node_id = f"node_{func_name}_{uuid.uuid4().hex[:8]}"

    # 统一归一化入参
    norm = normalize_call_arguments(call_node, node_def)
    input_constants: Dict[str, str] = {}
    input_ports: List[PortModel] = []

    if norm.has_variadic:
        # 为每个归一化的位置参数创建数字端口，并写入可静态提取的常量
        for dst_port, expr in norm.positional:
            if not any(p.name == dst_port for p in input_ports):
                input_ports.append(PortModel(name=dst_port, is_input=True))
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[dst_port] = str(val)
        # 为关键字参数创建命名端口并写入常量（若可静态提取）
        for pname, expr in norm.keywords.items():
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[pname] = str(val)
                if not any(p.name == pname for p in input_ports):
                    input_ports.append(PortModel(name=pname, is_input=True))
        # 若未创建任何变参位置端口，为变参节点补一个最小合法端口：
        # - 一般变参节点（如“拼装列表”）→ 端口名 "0"
        # - 键值对变参节点（如“拼装字典”）→ 端口名 "键0" 与 "值0"
        if norm.created_variadic_count == 0:
            # 优先探测是否为“键/值成对”的变参节点
            from .arg_normalizer import _detect_key_value_variadic_pattern  # type: ignore[attr-defined]

            key_value_meta = _detect_key_value_variadic_pattern(node_def) if node_def else None  # type: ignore[arg-type]
            if key_value_meta is not None:
                key_prefix, value_prefix, start_index = key_value_meta
                key_name = f"{key_prefix}{int(start_index)}"
                value_name = f"{value_prefix}{int(start_index)}"
                if not any(p.name == key_name for p in input_ports):
                    input_ports.append(PortModel(name=key_name, is_input=True))
                    input_constants[key_name] = "0"
                if not any(p.name == value_name for p in input_ports):
                    input_ports.append(PortModel(name=value_name, is_input=True))
                    input_constants[value_name] = "0"
            else:
                if not any(p.name == "0" for p in input_ports):
                    input_ports.append(PortModel(name="0", is_input=True))
                    input_constants["0"] = "0"
    else:
        # 非变参：端口直接来自定义；仅回填常量
        for pname in node_def.inputs:
            if "~" in pname:
                continue
            input_ports.append(PortModel(name=pname, is_input=True))
        
        # 动态端口节点（如 修改结构体、发送信号）：为代码中传递的关键字参数创建动态输入端口
        # 这些端口不在 node_def.inputs 的静态定义中，但在代码调用中被使用
        dynamic_port_type_value = getattr(node_def, "dynamic_port_type", "")
        existing_port_names = {p.name for p in input_ports}
        
        # 位置参数回填
        for dst_port, expr in norm.positional:
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[dst_port] = str(val)
        # 关键字参数回填（覆盖同名）；对于动态端口节点，同时创建对应的输入端口
        for pname, expr in norm.keywords.items():
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[pname] = str(val)
            # 动态端口节点：为不在静态定义中的关键字参数创建输入端口
            if dynamic_port_type_value and pname not in existing_port_names:
                input_ports.append(PortModel(name=pname, is_input=True))
                existing_port_names.add(pname)

    output_ports: List[PortModel] = [PortModel(name=o, is_input=False) for o in node_def.outputs]

    node = NodeModel(
        id=node_id,
        title=(node_def.name if node_def else func_name),
        category=node_def.category,
        pos=(100.0, 100.0),
        inputs=input_ports,
        outputs=output_ports,
        input_constants=input_constants,
    )

    # 源码行号：直接从调用表达式记录，便于错误定位
    node.source_lineno = getattr(call_node, 'lineno', 0)
    node.source_end_lineno = getattr(call_node, 'end_lineno', getattr(call_node, 'lineno', 0))

    if hasattr(node_def, 'composite_id') and node_def.composite_id:
        node.composite_id = node_def.composite_id

    return node


def extract_nested_nodes(
    call_node: ast.Call,
    ctx: FactoryContext,
    validators: Validators,
    env: VarEnv,
) -> Tuple[List[NodeModel], List[EdgeModel], Dict[str, NodeModel]]:
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []
    param_node_map: Dict[str, NodeModel] = {}

    func_name: Optional[str] = None
    if isinstance(call_node.func, ast.Name):
        func_name = call_node.func.id
    elif isinstance(call_node.func, ast.Attribute):
        func_name = call_node.func.attr
    full_key = ctx.node_name_index.get(func_name) if func_name else None
    node_def = ctx.node_library.get(full_key) if full_key else None

    # 归一化当前调用的参数映射，以便对“嵌套调用 → 父节点输入端口”的目标端口名保持与
    # normalize_call_arguments 完全一致（含变参与键值对变参）。
    norm_for_current = normalize_call_arguments(call_node, node_def) if node_def else None
    positional_iter: Optional[Iterator[Tuple[str, ast.AST]]] = None
    if norm_for_current is not None:
        positional_iter = iter(norm_for_current.positional)

    # 关键字参数中的嵌套调用
    for keyword in call_node.keywords:
        param_name = keyword.arg
        if isinstance(keyword.value, ast.Call):
            nested_node = create_node_from_call(keyword.value, ctx, validators, env=env)
            if nested_node:
                nodes.append(nested_node)
                if param_name is not None:
                    param_node_map[param_name] = nested_node

                sub_nodes, sub_edges, sub_param_node_map = extract_nested_nodes(
                    keyword.value,
                    ctx,
                    validators,
                    env,
                )
                nodes.extend(sub_nodes)
                edges.extend(sub_edges)

                nested_data_edges = create_data_edges_for_node_enhanced(
                    nested_node,
                    keyword.value,
                    sub_param_node_map,
                    ctx.node_library,
                    ctx.node_name_index,
                    env,
                )
                edges.extend(nested_data_edges)

    # 位置参数中的嵌套调用（跳过保留参数：self / game / owner_entity / self.game / self.owner_entity）
    if getattr(call_node, "args", None):
        # 使用与 normalize_call_arguments 完全一致的顺序与过滤规则：
        # - 仅对“非保留参数”推进迭代器
        # - 变参/键值对变参节点的目标端口名已经在 normalize_call_arguments 中计算好
        for argument_expr in call_node.args:
            if is_reserved_argument(argument_expr):
                continue

            target_port: Optional[str] = None
            if positional_iter is not None:
                try:
                    target_port, _ = next(positional_iter)
                except StopIteration:
                    target_port = None

            if target_port is None:
                continue

            if isinstance(argument_expr, ast.Call):
                nested_node = create_node_from_call(argument_expr, ctx, validators, env=env)
                if nested_node:
                    nodes.append(nested_node)
                    param_node_map[target_port] = nested_node

                    sub_nodes, sub_edges, sub_param_node_map = extract_nested_nodes(
                        argument_expr,
                        ctx,
                        validators,
                        env,
                    )
                    nodes.extend(sub_nodes)
                    edges.extend(sub_edges)

                    nested_data_edges = create_data_edges_for_node_enhanced(
                        nested_node,
                        argument_expr,
                        sub_param_node_map,
                        ctx.node_library,
                        ctx.node_name_index,
                        env,
                    )
                    edges.extend(nested_data_edges)

    return nodes, edges, param_node_map



