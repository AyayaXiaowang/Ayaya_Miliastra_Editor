from __future__ import annotations

from collections import deque
import json
import keyword
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from engine.graph.common import (
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
    node_name_index_from_library,
)
from engine.graph.port_type_effective_resolver import (
    build_port_type_overrides,
    resolve_override_type_for_node_port,
)
from engine.graph.models import GraphModel, NodeModel
from engine.graph.semantic import SEMANTIC_SIGNAL_ID_CONSTANT_KEY
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.utils.name_utils import make_valid_identifier
from engine.utils.workspace import render_workspace_bootstrap_lines

from engine.graph.reverse_codegen._common import (
    ReverseGraphCodeError,
    ReverseGraphCodeOptions,
    _is_layout_artifact_node_id,
    _try_resolve_node_def,
)
from engine.graph.reverse_codegen.emitter import _StructuredEventEmitter


def generate_graph_code_from_model(
    model: GraphModel,
    *,
    node_library: Dict[str, NodeDef],
    options: Optional[ReverseGraphCodeOptions] = None,
) -> str:
    """从 GraphModel 生成“类结构 Python Graph Code”。"""
    if options is None:
        options = ReverseGraphCodeOptions()

    scope = str(options.scope or _infer_scope_from_model(model) or "server").strip().lower()
    if scope not in {"server", "client"}:
        raise ReverseGraphCodeError(f"不支持的 scope：{scope!r}（仅支持 'server'/'client'）")

    node_name_index = node_name_index_from_library(node_library, scope=scope)
    call_name_candidates_by_identity = _build_call_name_candidates_by_identity(node_library)
    composite_specs, composite_alias_by_id = _collect_composite_instance_specs(
        model=model,
        node_library=node_library,
    )

    # 事件流分组：按“流程边”收集成员，并闭包式纳入数据依赖。
    #
    # 注意：复合节点可能存在不含“流程”字样的流程出口（如“分支为0/分支为1”），
    # 必须使用 context-aware 的流程端口判定，否则事件流会漏收节点。
    grouped = _group_nodes_by_event_with_context(
        model=model,
        node_library=node_library,
        include_data_dependencies=True,
    )
    if not grouped:
        raise ReverseGraphCodeError("输入图未包含任何事件节点（category='事件节点'）")

    # 覆盖度检查：不支持“无事件归属”的孤立子图（避免静默丢节点）。
    # 例外：布局层插入的 relay/copy 属于非语义结构增强，允许不参与覆盖度。
    layout_artifacts: set[str] = set()
    for node_id, node in (getattr(model, "nodes", None) or {}).items():
        if node is None:
            continue
        if _is_layout_artifact_node_id(node_id=str(node_id), node=node):
            layout_artifacts.add(str(node_id))
    covered: set[str] = set()
    for members in grouped.values():
        covered.update(str(x) for x in (members or []))
    missing = [node_id for node_id in model.nodes.keys() if node_id not in covered and node_id not in layout_artifacts]
    if missing:
        # 容忍“事件流不可达但仍属于图”的孤立子图（例如 client 校准图中使用『节点图开始』作为额外流程入口）。
        # 这些节点会被挂到某个事件方法里作为“额外流程入口序列”生成；若无法稳定生成，后续会 fail-closed。
        graph_nodes = dict(getattr(model, "nodes", {}) or {})
        graph_edges = list((getattr(model, "edges", {}) or {}).values())

        def _is_data_edge(edge) -> bool:
            src_node = graph_nodes.get(str(getattr(edge, "src_node", "") or ""))
            dst_node = graph_nodes.get(str(getattr(edge, "dst_node", "") or ""))
            if src_node is None or dst_node is None:
                return False
            src_port = str(getattr(edge, "src_port", "") or "")
            dst_port = str(getattr(edge, "dst_port", "") or "")
            if not src_port or not dst_port:
                return False
            return bool(
                (not is_flow_port_with_context(src_node, src_port, True, node_library))
                and (not is_flow_port_with_context(dst_node, dst_port, False, node_library))
            )

        event_order = _pick_event_order(model, grouped)
        if not event_order:
            # grouped 非空时这里理论上不会发生，仅兜底
            raise ReverseGraphCodeError("输入图未包含任何事件节点（category='事件节点'）")

        # 若 missing 子图显式依赖某个事件节点输出（data edge from event -> missing），优先挂到该事件；
        # 否则挂到第一个事件（稳定且可预期）。
        referenced_events: set[str] = set()
        missing_set = set(str(x) for x in missing)
        for edge in graph_edges:
            dst_id = str(getattr(edge, "dst_node", "") or "")
            if dst_id not in missing_set:
                continue
            src_id = str(getattr(edge, "src_node", "") or "")
            src_node = graph_nodes.get(src_id)
            if src_node is None:
                continue
            if str(getattr(src_node, "category", "") or "") != "事件节点":
                continue
            if not _is_data_edge(edge):
                continue
            referenced_events.add(src_id)

        if len(referenced_events) > 1:
            raise ReverseGraphCodeError(
                "未归属事件流的子图同时依赖多个事件节点输出，无法可靠归属："
                + ", ".join(sorted(referenced_events))
            )

        target_event = next(iter(referenced_events)) if referenced_events else str(event_order[0])
        # 需要把 layout 产物一并纳入 member_set：
        # - 它们可能出现在“孤立子图”的数据边路径中（例如 copy_block/relay），
        # - 虽然不应被写入为真实语义节点，但在构建 data_in_edge 归一化索引时必须可见。
        attach_set = missing_set | set(layout_artifacts)
        grouped[target_event] = sorted(set(grouped.get(target_event, []) or []) | attach_set)

    graph_id = str(getattr(model, "graph_id", "") or "").strip()
    graph_name = str(getattr(model, "graph_name", "") or "").strip()
    description = str(getattr(model, "description", "") or "").strip()
    folder_path = str((model.metadata or {}).get("folder_path", "") or "").strip()

    class_name = _pick_class_name(options.class_name, graph_name=graph_name, graph_id=graph_id)
    prelude_import = (
        "from app.runtime.engine.graph_prelude_client import *  # noqa: F401,F403"
        if scope == "client"
        else "from app.runtime.engine.graph_prelude_server import *  # noqa: F401,F403"
    )

    lines: List[str] = []

    # ===== 模块 docstring：解析器从这里提取 graph_id/name/type/description =====
    lines.append('"""')
    if graph_id:
        lines.append(f"graph_id: {graph_id}")
    if graph_name:
        lines.append(f"graph_name: {graph_name}")
    lines.append(f"graph_type: {scope}")
    if folder_path:
        lines.append(f"folder_path: {folder_path}")
    if description:
        lines.append(f"description: {description}")
    lines.append('"""')
    lines.append("")

    lines.append("from __future__ import annotations")
    lines.append("")

    if options.include_sys_path_bootstrap:
        lines.extend(
            render_workspace_bootstrap_lines(
                project_root_var="PROJECT_ROOT",
                assets_root_var="ASSETS_ROOT",
            )
        )
        lines.append("")

    lines.append(prelude_import)
    lines.append("")

    # ===== 图变量：唯一来源 GRAPH_VARIABLES =====
    lines.extend(_render_graph_variables_lines(model))
    lines.append("")

    # ===== 节点图类 =====
    lines.append(f"class {class_name}:")
    lines.append("    def __init__(self, game, owner_entity):")
    lines.append("        self.game = game")
    lines.append("        self.owner_entity = owner_entity")
    lines.append("")
    # 复合节点实例声明：用于 match self.<实例>.<入口>(...) 与普通复合调用的解析（env.composite_instances）
    # 注意：即使关闭 init 校验，也必须保留复合实例声明，否则复合节点方法调用会被当作 Python 原生方法调用拒绝解析。
    lines.extend(_render_composite_instance_lines(composite_specs))
    if options.include_validate_node_graph_in_init:
        lines.append("        from app.runtime.engine.node_graph_validator import validate_node_graph")
        lines.append("")
        lines.append("        validate_node_graph(self.__class__)")
    else:
        lines.append("        return")
    lines.append("")

    # 事件顺序：优先使用 event_flow_order；否则按 title 稳定排序
    event_ids = _pick_event_order(model, grouped)

    for event_id in event_ids:
        event_node = model.nodes.get(event_id)
        if event_node is None:
            continue
        _render_event_method_lines(
            lines,
            model=model,
            event_node=event_node,
            member_ids=grouped.get(event_id, []),
            node_library=node_library,
            node_name_index=node_name_index,
            call_name_candidates_by_identity=call_name_candidates_by_identity,
            composite_alias_by_id=composite_alias_by_id,
            options=options,
        )
        lines.append("")

    # ===== register_handlers =====
    lines.extend(_render_register_handlers_lines(model=model, event_ids=event_ids))
    lines.append("")

    if options.include_main_validate_cli:
        lines.extend(_render_main_validate_cli_lines())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _infer_scope_from_model(model: GraphModel) -> str:
    meta = getattr(model, "metadata", {}) or {}
    scope = meta.get("graph_type") or meta.get("scope") or ""
    return str(scope or "").strip().lower()


def _group_nodes_by_event_with_context(
    *,
    model: GraphModel,
    node_library: Dict[str, NodeDef],
    include_data_dependencies: bool,
) -> Dict[str, List[str]]:
    """按事件节点分组收集成员集合（使用 context-aware 流程端口判定）。"""
    graph_nodes = dict(getattr(model, "nodes", {}) or {})
    graph_edges = list((getattr(model, "edges", {}) or {}).values())

    event_nodes = [n for n in graph_nodes.values() if str(getattr(n, "category", "") or "") == "事件节点"]
    grouped: Dict[str, List[str]] = {}

    def _is_flow_edge(edge) -> bool:
        src_node = graph_nodes.get(str(getattr(edge, "src_node", "") or ""))
        dst_node = graph_nodes.get(str(getattr(edge, "dst_node", "") or ""))
        if src_node is None or dst_node is None:
            return False
        src_port = str(getattr(edge, "src_port", "") or "")
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if not src_port or not dst_port:
            return False
        return bool(
            is_flow_port_with_context(src_node, src_port, True, node_library)
            and is_flow_port_with_context(dst_node, dst_port, False, node_library)
        )

    def _is_data_edge(edge) -> bool:
        src_node = graph_nodes.get(str(getattr(edge, "src_node", "") or ""))
        dst_node = graph_nodes.get(str(getattr(edge, "dst_node", "") or ""))
        if src_node is None or dst_node is None:
            return False
        src_port = str(getattr(edge, "src_port", "") or "")
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if not src_port or not dst_port:
            return False
        return bool(
            (not is_flow_port_with_context(src_node, src_port, True, node_library))
            and (not is_flow_port_with_context(dst_node, dst_port, False, node_library))
        )

    for event_node in event_nodes:
        start_id = str(getattr(event_node, "id", "") or "")
        if not start_id:
            continue
        visited: set[str] = set()
        q = deque([start_id])
        while q:
            node_id = q.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            for edge in graph_edges:
                if str(getattr(edge, "src_node", "") or "") != node_id:
                    continue
                if _is_flow_edge(edge):
                    q.append(str(getattr(edge, "dst_node", "") or ""))

        if include_data_dependencies and visited:
            changed = True
            while changed:
                changed = False
                for edge in graph_edges:
                    dst_node_id = str(getattr(edge, "dst_node", "") or "")
                    if dst_node_id not in visited:
                        continue
                    if not _is_data_edge(edge):
                        continue
                    src_node_id = str(getattr(edge, "src_node", "") or "")
                    if src_node_id and src_node_id not in visited:
                        visited.add(src_node_id)
                        changed = True

        grouped[start_id] = sorted(visited)

    return grouped


def _render_main_validate_cli_lines() -> List[str]:
    return [
        "if __name__ == '__main__':",
        "    from app.runtime.engine.node_graph_validator import validate_file_cli",
        "    raise SystemExit(validate_file_cli(__file__))",
    ]


def _render_graph_variables_lines(model: GraphModel) -> List[str]:
    variables = list(getattr(model, "graph_variables", []) or [])
    lines: List[str] = []
    lines.append("GRAPH_VARIABLES: list[GraphVariableConfig] = [")
    for item in variables:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "")
        variable_type = str(item.get("variable_type", "") or "")
        if not name or not variable_type:
            continue
        lines.append("    GraphVariableConfig(")
        lines.append(f"        name={name!r},")
        lines.append(f"        variable_type={variable_type!r},")
        if "default_value" in item:
            lines.append(f"        default_value={_format_json_constant(item.get('default_value'))},")
        desc = str(item.get("description", "") or "")
        if desc:
            lines.append(f"        description={desc!r},")
        is_exposed = bool(item.get("is_exposed", False))
        if is_exposed:
            lines.append("        is_exposed=True,")
        struct_name = str(item.get("struct_name", "") or "")
        if struct_name:
            lines.append(f"        struct_name={struct_name!r},")
        dict_key_type = str(item.get("dict_key_type", "") or "")
        dict_value_type = str(item.get("dict_value_type", "") or "")
        if dict_key_type:
            lines.append(f"        dict_key_type={dict_key_type!r},")
        if dict_value_type:
            lines.append(f"        dict_value_type={dict_value_type!r},")
        lines.append("    ),")
    lines.append("]")
    return lines


def _pick_class_name(requested: str, *, graph_name: str, graph_id: str) -> str:
    requested_text = str(requested or "").strip()
    if requested_text:
        if not requested_text.isidentifier() or keyword.iskeyword(requested_text):
            raise ReverseGraphCodeError(f"class_name 不是合法 Python 标识符：{requested_text!r}")
        return requested_text

    candidate = str(graph_name or "").strip()
    if candidate and candidate.isidentifier() and (not keyword.iskeyword(candidate)):
        return candidate

    # 回退：尽量保持可读且稳定
    fallback_seed = candidate or graph_id or "NodeGraph"
    safe = make_valid_identifier(fallback_seed)
    if not safe or safe == "_":
        safe = "NodeGraph"
    if keyword.iskeyword(safe):
        safe = f"{safe}_graph"
    return safe


def _pick_event_order(model: GraphModel, grouped: Mapping[str, Sequence[str]]) -> List[str]:
    order = list(getattr(model, "event_flow_order", []) or [])
    order = [x for x in order if x in grouped]
    if order:
        return order

    # 回退：按事件节点 title 稳定排序
    event_nodes: List[NodeModel] = []
    for event_id in grouped.keys():
        node = model.nodes.get(event_id)
        if node is not None:
            event_nodes.append(node)
    event_nodes.sort(key=lambda n: str(getattr(n, "title", "") or ""))
    return [n.id for n in event_nodes]


def _collect_composite_instance_specs(
    *,
    model: GraphModel,
    node_library: Dict[str, NodeDef],
) -> Tuple[List[Tuple[str, str, str]], Dict[str, str]]:
    """收集复合节点实例声明信息。

    Returns:
        (specs, alias_by_composite_id)
        - specs: [(composite_id, class_name, alias), ...]（稳定排序）
        - alias_by_composite_id: {composite_id: alias}
    """
    # 先收集“用到的复合节点”集合：以 composite_id 为主键，避免同名冲突。
    composite_id_to_class: Dict[str, str] = {}
    for node in (getattr(model, "nodes", None) or {}).values():
        if node is None:
            continue
        node_def = _try_resolve_node_def(node=node, node_library=node_library)
        if node_def is None:
            continue
        if not bool(getattr(node_def, "is_composite", False)):
            continue
        class_name = str(getattr(node_def, "name", "") or "").strip() or str(getattr(node, "title", "") or "").strip()
        if not class_name:
            continue
        if not class_name.isidentifier() or keyword.iskeyword(class_name):
            raise ReverseGraphCodeError(f"复合节点类名不可表示为 Python 标识符：{class_name!r}")
        composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(getattr(node, "composite_id", "") or "").strip()
        if not composite_id:
            # 兜底：缺少稳定 ID 时退化为使用 class_name 作为“实例键”（仍然稳定可复现）
            composite_id = class_name
        composite_id_to_class.setdefault(composite_id, class_name)

    if not composite_id_to_class:
        return ([], {})

    # 稳定排序：先按类名再按 composite_id（避免输出随 dict 顺序抖动）
    ordered = sorted(composite_id_to_class.items(), key=lambda item: (item[1], item[0]))
    used_aliases: set[str] = set()
    specs: List[Tuple[str, str, str]] = []
    alias_by_id: Dict[str, str] = {}
    for composite_id, class_name in ordered:
        alias = make_valid_identifier(class_name) or "复合实例"
        if keyword.iskeyword(alias):
            alias = f"{alias}_实例"
        base = alias
        counter = 1
        while alias in used_aliases or keyword.iskeyword(alias):
            counter += 1
            alias = f"{base}_{counter}"
        used_aliases.add(alias)
        alias_by_id[composite_id] = alias
        specs.append((composite_id, class_name, alias))

    return (specs, alias_by_id)


def _render_composite_instance_lines(composite_specs: Sequence[Tuple[str, str, str]]) -> List[str]:
    """在 __init__ 中生成复合节点实例声明（解析器用于建立 env.composite_instances）。"""
    specs = list(composite_specs or [])
    if not specs:
        return []

    lines: List[str] = []
    for _composite_id, class_name, alias in specs:
        # 仅用于解析：不强制要求可运行（无 import）。但必须是 `self.xxx = ClassName(...)` 形式。
        lines.append(f"        self.{alias} = {class_name}(game, owner_entity)")

    lines.append("")
    return lines


def _render_event_method_lines(
    out_lines: List[str],
    *,
    model: GraphModel,
    event_node: NodeModel,
    member_ids: Sequence[str],
    node_library: Dict[str, NodeDef],
    node_name_index: Dict[str, str],
    call_name_candidates_by_identity: Dict[int, List[str]],
    composite_alias_by_id: Mapping[str, str],
    options: ReverseGraphCodeOptions,
) -> None:
    event_title = str(getattr(event_node, "title", "") or "").strip()
    if not event_title:
        raise ReverseGraphCodeError("事件节点缺少 title")

    method_name = f"on_{event_title}"
    if not method_name.isidentifier() or keyword.iskeyword(method_name):
        raise ReverseGraphCodeError(f"事件方法名不可表示为 Python 标识符：{method_name!r}")

    # 事件方法形参：取事件节点的数据输出端口（排除流程端口）
    overrides_mapping = build_port_type_overrides(model)
    params: List[str] = []
    for port in (event_node.outputs or []):
        port_name = str(getattr(port, "name", "") or "")
        if not port_name:
            continue
        if is_flow_port_with_context(event_node, port_name, True, node_library):
            continue
        if not port_name.isidentifier() or keyword.iskeyword(port_name):
            raise ReverseGraphCodeError(
                f"事件输出端口名不可作为 Python 形参：{event_title}.{port_name}"
            )
        # 关键：严格模式下事件输出端口不得残留“泛型”；反向生成必须输出中文类型注解，
        # 否则事件节点（尤其是【监听信号】）会因端口类型未实例化而 fail-closed。
        type_text = resolve_override_type_for_node_port(overrides_mapping, event_node.id, port_name)
        if not type_text:
            type_text = str((getattr(event_node, "output_types", None) or {}).get(port_name, "") or "").strip()
        if type_text:
            params.append(f'{port_name}: "{type_text}"')
        else:
            params.append(port_name)

    out_lines.append(f"    # ---------------------------- 事件：{event_title} ----------------------------")
    signature = ", ".join(["self"] + params) if params else "self"
    out_lines.append(f"    def {method_name}({signature}):")

    # VarEnv：事件输出变量天然存在
    var_mapping: Dict[Tuple[str, str], str] = {}
    for port in (event_node.outputs or []):
        name = str(getattr(port, "name", "") or "")
        if not name or is_flow_port_with_context(event_node, name, True, node_library):
            continue
        var_mapping[(event_node.id, name)] = name

    member_set = set(str(x) for x in (member_ids or []))
    emitter = _StructuredEventEmitter(
        model=model,
        member_set=member_set,
        node_library=node_library,
        node_name_index=node_name_index,
        call_name_candidates_by_identity=call_name_candidates_by_identity,
        composite_alias_by_id=dict(composite_alias_by_id or {}),
        options=options,
    )
    return_expr = emitter.emit_event_body(
        out_lines=out_lines,
        event_node=event_node,
        var_mapping=var_mapping,
        used_var_names=set(var_mapping.values()),
        indent="        ",
    )
    if return_expr:
        out_lines.append(f"        return {return_expr}")
    else:
        out_lines.append("        return")


def _render_register_handlers_lines(*, model: GraphModel, event_ids: Sequence[str]) -> List[str]:
    lines: List[str] = []
    lines.append("    # ---------------------------- 注册事件处理器 ----------------------------")
    lines.append("    def register_handlers(self):")
    for event_id in event_ids:
        node = model.nodes.get(event_id)
        if node is None:
            continue
        event_title = str(getattr(node, "title", "") or "").strip()
        if not event_title:
            continue

        handler_method = f"self.on_{event_title}"
        if event_title == SIGNAL_LISTEN_NODE_TITLE:
            key = _pick_signal_listen_event_key(model=model, event_node=node)
        else:
            key = event_title
        lines.append("        self.game.register_event_handler(")
        lines.append(f"            {key!r},")
        lines.append(f"            {handler_method},")
        lines.append("            owner=self.owner_entity,")
        lines.append("        )")
    if len(lines) == 2:
        lines.append("        return")
    return lines


def _pick_signal_listen_event_key(*, model: GraphModel, event_node: NodeModel) -> str:
    # 优先：GraphSemanticPass 生成的 metadata["signal_bindings"][node_id]["signal_id"]
    meta = getattr(model, "metadata", {}) or {}
    bindings = meta.get("signal_bindings")
    if isinstance(bindings, dict):
        info = bindings.get(str(event_node.id))
        if isinstance(info, dict):
            signal_id = info.get("signal_id")
            if isinstance(signal_id, str) and signal_id.strip():
                return signal_id.strip()

    # 其次：节点常量隐藏键（用于语义 pass 推导）
    consts = getattr(event_node, "input_constants", {}) or {}
    raw_id = consts.get(SEMANTIC_SIGNAL_ID_CONSTANT_KEY)
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()

    # 再次：信号名展示端口（如果存在）
    raw_name = consts.get(SIGNAL_NAME_PORT_NAME)
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()

    raise ReverseGraphCodeError("监听信号事件缺少 signal_id/信号名，无法生成 register_handlers 绑定")


def _format_json_constant(value: Any) -> str:
    # 生成“可被 AST 提取”的字面量：尽量输出 JSON 风格，必要时回退为 Python repr。
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return repr(value)


def _build_call_name_candidates_by_identity(node_library: Dict[str, NodeDef]) -> Dict[int, List[str]]:
    candidates: Dict[int, set[str]] = {}
    for full_key, node_def in (node_library or {}).items():
        if not isinstance(full_key, str) or "/" not in full_key:
            continue
        _, name_part = full_key.split("/", 1)
        base_name = name_part.split("#", 1)[0]
        if not base_name:
            continue

        identity = id(node_def)
        bucket = candidates.setdefault(identity, set())

        # 1) 原始名称（若可作为调用名）
        if base_name.isidentifier() and (not keyword.iskeyword(base_name)):
            bucket.add(base_name)

        # 2) 兼容：名称中包含 '/' 的节点（节点库会为其提供“去斜杠别名”调用）
        # 例如：NodeDef.name="允许/禁止玩家复苏" → Graph Code 调用通常写作 "允许禁止玩家复苏(...)"
        if "/" in base_name:
            alias = base_name.replace("/", "")
            if alias.isidentifier() and (not keyword.iskeyword(alias)):
                bucket.add(alias)
    return {k: sorted(v, key=_call_name_sort_key) for k, v in candidates.items()}


def _call_name_sort_key(name: str) -> Tuple[int, int, str]:
    has_underscore = 1 if "_" in name else 0
    return (has_underscore, len(name), name)

