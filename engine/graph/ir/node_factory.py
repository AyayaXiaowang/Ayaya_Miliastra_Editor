from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Iterator, Mapping

from engine.graph.models import NodeModel, PortModel, EdgeModel, NodeDefRef
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes import get_canonical_node_def_key
from engine.graph.common import STRUCT_NAME_PORT_NAME
from .var_env import VarEnv
from .validators import Validators
from .edge_router import create_data_edges_for_node_enhanced
from .arg_normalizer import normalize_call_arguments, is_reserved_argument
from .composite_builder import create_composite_node_from_instance_call


@dataclass
class FactoryContext:
    node_library: Dict[str, NodeDef]
    node_name_index: Dict[str, str]
    verbose: bool = False
    # Graph Code 的作用域（server/client），用于在 IR 层处理“同名节点在不同 scope 下端口不兼容”的语义分支
    # （例如：局部变量建模的【获取/设置局部变量】在 server/client 下端口名不同）。
    graph_scope: str = "server"
    # Graph Code 元信息：用于在 IR 层按图类型做轻量语义分支（例如 client 过滤器图的 return → 结束节点建模）。
    # 说明：该字段由上层解析器在每次 parse_code(...) 入口处写入。
    graph_folder_path: str = ""
    # 注意：语义元数据（signal_bindings/struct_bindings）不在 IR 层写入，
    # 统一由 `engine.graph.semantic.GraphSemanticPass` 在更高层的明确阶段生成。


def _build_node_def_ref(node_def: NodeDef) -> NodeDefRef:
    """从 NodeDef 构造稳定 NodeDefRef（唯一真源）。"""
    if bool(getattr(node_def, "is_composite", False)):
        composite_id = str(getattr(node_def, "composite_id", "") or "").strip()
        if not composite_id:
            raise ValueError(f"复合节点 NodeDef 缺少 composite_id：{getattr(node_def, 'category', '')}/{getattr(node_def, 'name', '')}")
        return NodeDefRef(kind="composite", key=composite_id)
    return NodeDefRef(kind="builtin", key=get_canonical_node_def_key(node_def))


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
    #
    # 注意：Graph Code 支持形参写中文类型注解，例如 `整数参数: "整数"`。
    # 但在启用 `from __future__ import annotations` 时，AST 中的 annotation 可能为 ast.Name，
    # 而不是 ast.Constant。我们仍应保留端口名为“参数名”，类型实例化交由
    # register_event_outputs(...) 统一处理（写入 port_type_overrides）。
    for arg in method.args.args[1:]:
        output_ports.append(PortModel(name=arg.arg, is_input=False))

    node = NodeModel(
        id=node_id,
        title=event_name,
        category="事件节点",
        node_def_ref=_build_node_def_ref(node_def) if node_def is not None else NodeDefRef(kind="event", key=str(event_name)),
        pos=(100.0, 100.0),
        inputs=input_ports,
        outputs=output_ports,
    )
    # 源码行号：用于 UI 定位与错误提示（事件节点对应 handler 方法定义范围）
    node.source_lineno = getattr(method, "lineno", 0) or 0
    node.source_end_lineno = getattr(method, "end_lineno", node.source_lineno) or node.source_lineno
    return node


def register_event_outputs(
    event_node: NodeModel,
    method: ast.FunctionDef,
    env: VarEnv,
    *,
    graph_model: object | None = None,
) -> None:
    """注册事件节点的数据输出，并从函数参数注解实例化端口类型（写入 port_type_overrides）。"""
    for i, arg in enumerate(method.args.args[1:]):  # 跳过 self
        port_index = i + 1  # 0 是流程出
        if len(event_node.outputs) <= port_index:
            continue

        port_name = event_node.outputs[port_index].name
        env.set_variable(arg.arg, event_node.id, port_name)

        # 形参注解仅支持“字符串常量”形式：参数名: "整数"
        annotation_expr = getattr(arg, "annotation", None)
        if not (
            isinstance(annotation_expr, ast.Constant)
            and isinstance(getattr(annotation_expr, "value", None), str)
        ):
            continue
        annotation_text = str(annotation_expr.value or "").strip()
        if not annotation_text or annotation_text == "泛型":
            continue

        if graph_model is None:
            continue
        metadata = getattr(graph_model, "metadata", None)
        if not isinstance(metadata, dict):
            continue

        overrides_raw = metadata.get("port_type_overrides")
        overrides: Dict[str, Dict[str, str]] = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}
        node_overrides = overrides.get(event_node.id)
        node_overrides = dict(node_overrides) if isinstance(node_overrides, dict) else {}
        existing = str(node_overrides.get(str(port_name), "") or "").strip()

        # 若已有更具体类型则不覆盖；若已有“泛型”占位则允许被具体类型覆盖
        if (not existing) or existing == "泛型":
            node_overrides[str(port_name)] = annotation_text
            overrides[event_node.id] = node_overrides
            metadata["port_type_overrides"] = overrides


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
        # 支持“嵌套复合节点调用”：
        # - 当复合节点实例方法调用被用作其它节点入参（例如 `加法运算(..., 左值=self.<复合实例>.<入口>(...))`）
        #   时，必须在此处将其物化为 NodeModel，否则父节点会出现“输入缺少数据来源”。
        #
        # 注意：
        # - 这不会放开“复合节点内部嵌套复合节点”的限制：该限制由校验规则
        #   `CompositeTypesAndNestingRule` 负责阻断。
        if env is not None:
            composite_node = create_composite_node_from_instance_call(call_node, ctx.node_library, env)
            if composite_node is not None:
                return composite_node
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
    # 常量值：保留原始 Python 类型（int/float/bool/str/None/容器），避免数字常量在此阶段被 str() 造成类型丢失。
    # 说明：代码生成与 UI 展示层会在需要时再做 format/序列化。
    input_constants: Dict[str, Any] = {}
    input_ports: List[PortModel] = []

    if norm.has_variadic:
        # 为每个归一化的位置参数创建数字端口，并写入可静态提取的常量
        for dst_port, expr in norm.positional:
            if not any(p.name == dst_port for p in input_ports):
                input_ports.append(PortModel(name=dst_port, is_input=True))
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[dst_port] = val
        # 为关键字参数创建命名端口并写入常量（若可静态提取）
        for pname, expr in norm.keywords.items():
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[pname] = val
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
                input_constants[dst_port] = val
        # 关键字参数回填（覆盖同名）；对于动态端口节点，同时创建对应的输入端口
        for pname, expr in norm.keywords.items():
            val = _extract_constant_value_with_env(expr, env)
            if val is not NOT_EXTRACTABLE:
                input_constants[pname] = val
            # 动态端口节点：为不在静态定义中的关键字参数创建输入端口
            # 结构体语义节点兼容：Graph Code 允许通过 `结构体名="xxx"` 传入绑定展示名，
            # 但新约定下该字段不再建模为真实输入端口（结构体节点仅保留一个结构体端口）。
            semantic_id = str(getattr(node_def, "semantic_id", "") or "").strip() if node_def else ""
            is_struct_node = semantic_id in {"struct.build", "struct.split", "struct.modify"}
            if dynamic_port_type_value and pname not in existing_port_names:
                if is_struct_node and pname == STRUCT_NAME_PORT_NAME:
                    continue
                input_ports.append(PortModel(name=pname, is_input=True))
                existing_port_names.add(pname)

    # input_defaults：为“可选输入端口”补齐默认常量（仅当调用未显式提供该端口常量时）。
    # 注意：
    # - 连线优先于常量：即便后续生成了数据边，执行/导出时也会优先使用连线来源；
    # - 这里仅做“缺省值建模”，不参与任何运行期判空逻辑。
    input_defaults = dict(getattr(node_def, "input_defaults", {}) or {})
    if input_defaults:
        existing_port_names = {p.name for p in (input_ports or [])}
        for port_name, default_value in input_defaults.items():
            port_text = str(port_name or "").strip()
            if not port_text:
                continue
            if port_text in {"流程入", "流程出"}:
                continue
            if "~" in port_text:
                continue
            if port_text not in existing_port_names:
                input_ports.append(PortModel(name=port_text, is_input=True))
                existing_port_names.add(port_text)
            if port_text not in input_constants:
                input_constants[port_text] = default_value

    output_ports: List[PortModel] = [PortModel(name=o, is_input=False) for o in node_def.outputs]

    node = NodeModel(
        id=node_id,
        title=(node_def.name if node_def else func_name),
        category=node_def.category,
        node_def_ref=_build_node_def_ref(node_def),
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



