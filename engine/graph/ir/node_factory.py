from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from engine.graph.models import NodeModel, PortModel, EdgeModel
from engine.nodes.node_definition_loader import NodeDef
from .var_env import VarEnv
from .validators import Validators
from .edge_router import create_data_edges_for_node
from .arg_normalizer import normalize_call_arguments


class _NotExtractable:
    """哨兵：表示无法静态提取常量值。"""
    pass


NOT_EXTRACTABLE = _NotExtractable()


@dataclass
class FactoryContext:
    node_library: Dict[str, NodeDef]
    node_name_index: Dict[str, str]
    verbose: bool = False


def create_event_node(event_name: str, method: ast.FunctionDef, ctx: FactoryContext) -> NodeModel:
    full_key = ctx.node_name_index.get(event_name)
    node_def = ctx.node_library.get(full_key) if full_key else None

    node_id = f"event_{event_name}_{uuid.uuid4().hex[:8]}"

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
        outputs=output_ports,
    )
    return node


def register_event_outputs(event_node: NodeModel, method: ast.FunctionDef, env: VarEnv) -> None:
    for i, arg in enumerate(method.args.args[1:]):  # 跳过 self
        port_index = i + 1  # 0 是流程出
        if len(event_node.outputs) > port_index:
            env.set_variable(arg.arg, event_node.id, event_node.outputs[port_index].name)


def extract_constant_value(value_node: ast.expr) -> Any:
    if isinstance(value_node, ast.Constant):
        return value_node.value
    if isinstance(value_node, ast.Str):
        return value_node.s
    if isinstance(value_node, ast.Num):
        return value_node.n
    if isinstance(value_node, ast.NameConstant):
        return value_node.value
    # 处理一元运算：支持数值的一元正负号（+/-常量）
    if isinstance(value_node, ast.UnaryOp):
        # 负号：-1、-1.0
        if isinstance(value_node.op, ast.USub):
            inner = extract_constant_value(value_node.operand)
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return -inner
            return NOT_EXTRACTABLE
        # 正号：+1、+1.0（可选，保持语义完整）
        if isinstance(value_node.op, ast.UAdd):
            inner = extract_constant_value(value_node.operand)
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return +inner
            return NOT_EXTRACTABLE
    if isinstance(value_node, ast.List):
        return [extract_constant_value(e) for e in value_node.elts]
    if isinstance(value_node, ast.Tuple):
        return tuple(extract_constant_value(e) for e in value_node.elts)
    if isinstance(value_node, ast.JoinedStr):
        return NOT_EXTRACTABLE
    if isinstance(value_node, ast.Attribute):
        # self.xxx 属性访问：仅对少数经过约定的字段做“伪常量”展开，其余统一视为不可静态提取，避免误把状态字段当成字面量。
        if isinstance(value_node.value, ast.Name) and value_node.value.id == 'self':
            attr_name = value_node.attr
            # owner_entity 在不少节点图中作为“当前所属实体”传递，这里保留成表达式字符串供上层按需特殊处理。
            if attr_name == "owner_entity":
                return f"self.{attr_name}"
            # 约定：以下划线开头的字段（例如 _定时器标识）更多用于临时状态/别名，不作为可编辑常量暴露到节点图。
            if attr_name.startswith("_"):
                return NOT_EXTRACTABLE
            # 其他公开字段按照字符串常量处理，供上层按需解析。
            return f"self.{attr_name}"
        return NOT_EXTRACTABLE
    if isinstance(value_node, ast.Name):
        return NOT_EXTRACTABLE
    return NOT_EXTRACTABLE


def create_node_from_call(call_node: ast.Call, ctx: FactoryContext, validators: Validators) -> Optional[NodeModel]:
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
            val = extract_constant_value(expr)
            if val is not NOT_EXTRACTABLE:
                input_constants[dst_port] = str(val)
        # 为关键字参数创建命名端口并写入常量（若可静态提取）
        for pname, expr in norm.keywords.items():
            val = extract_constant_value(expr)
            if val is not NOT_EXTRACTABLE:
                input_constants[pname] = str(val)
                if not any(p.name == pname for p in input_ports):
                    input_ports.append(PortModel(name=pname, is_input=True))
        # 若未创建任何数字端口，占位一个 "0"
        if norm.created_variadic_count == 0 and not any(p.name == "0" for p in input_ports):
            input_ports.append(PortModel(name="0", is_input=True))
            input_constants["0"] = "0"
    else:
        # 非变参：端口直接来自定义；仅回填常量
        for pname in node_def.inputs:
            if "~" in pname:
                continue
            input_ports.append(PortModel(name=pname, is_input=True))
        # 位置参数回填
        for dst_port, expr in norm.positional:
            val = extract_constant_value(expr)
            if val is not NOT_EXTRACTABLE:
                input_constants[dst_port] = str(val)
        # 关键字参数回填（覆盖同名）
        for pname, expr in norm.keywords.items():
            val = extract_constant_value(expr)
            if val is not NOT_EXTRACTABLE:
                input_constants[pname] = str(val)

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
    has_variadic = bool(node_def and any('~' in s for s in getattr(node_def, 'inputs', [])))
    data_params_for_normal: List[str] = []
    if node_def:
        data_params_for_normal = [p for p in node_def.inputs if p not in ["流程入", "流程出"] and '~' not in p]

    # 关键字参数中的嵌套调用
    for keyword in call_node.keywords:
        pname = keyword.arg
        if isinstance(keyword.value, ast.Call):
            nested = create_node_from_call(keyword.value, ctx, validators)
            if nested:
                nodes.append(nested)
                param_node_map[pname] = nested
                sub_nodes, sub_edges, sub_map = extract_nested_nodes(keyword.value, ctx, validators, env)
                nodes.extend(sub_nodes)
                edges.extend(sub_edges)
                edges.extend(create_data_edges_for_node(nested, keyword.value, env))
                for sub_param, sub_node in sub_map.items():
                    input_names = [p.name for p in nested.inputs]
                    if sub_param in input_names:
                        out_name = next((p.name for p in sub_node.outputs if '流程' not in p.name), None)
                        if out_name:
                            edges.append(EdgeModel(
                                id=str(uuid.uuid4()),
                                src_node=sub_node.id,
                                src_port=out_name,
                                dst_node=nested.id,
                                dst_port=sub_param,
                            ))

    # 位置参数中的嵌套调用（跳过 self.game）
    if getattr(call_node, 'args', None):
        for idx, pos_arg in enumerate(call_node.args):
            if idx == 0:
                continue
            if has_variadic:
                target_port = str(idx - 1)
            else:
                data_index = idx - 1
                if data_index >= len(data_params_for_normal):
                    continue
                target_port = data_params_for_normal[data_index]
            if isinstance(pos_arg, ast.Call):
                nested = create_node_from_call(pos_arg, ctx, validators)
                if nested:
                    nodes.append(nested)
                    param_node_map[target_port] = nested
                    sub_nodes, sub_edges, sub_map = extract_nested_nodes(pos_arg, ctx, validators, env)
                    nodes.extend(sub_nodes)
                    edges.extend(sub_edges)
                    edges.extend(create_data_edges_for_node(nested, pos_arg, env))
                    for sub_param, sub_node in sub_map.items():
                        input_names = [p.name for p in nested.inputs]
                        if sub_param in input_names:
                            out_name = next((p.name for p in sub_node.outputs if '流程' not in p.name), None)
                            if out_name:
                                edges.append(EdgeModel(
                                    id=str(uuid.uuid4()),
                                    src_node=sub_node.id,
                                    src_port=out_name,
                                    dst_node=nested.id,
                                    dst_port=sub_param,
                                ))

    return nodes, edges, param_node_map



