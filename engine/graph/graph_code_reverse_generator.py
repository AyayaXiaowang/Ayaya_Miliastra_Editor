from __future__ import annotations

from collections import deque
import hashlib
import json
import keyword
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from engine.graph.common import (
    BRANCH_NODE_NAMES,
    LOOP_NODE_NAMES,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
    format_constant,
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


class ReverseGraphCodeError(ValueError):
    """反向生成 Graph Code 失败（输入图超出当前支持范围或缺少必要信息）。"""


_LOCAL_VAR_RELAY_NODE_ID_PREFIX = "node_localvar_relay_block_"
_COPY_MARKER = "_copy_"


def _is_local_var_relay_node_id(node_id: object) -> bool:
    return isinstance(node_id, str) and node_id.startswith(_LOCAL_VAR_RELAY_NODE_ID_PREFIX)


def _is_data_node_copy(node: object) -> bool:
    return bool(getattr(node, "is_data_node_copy", False))


def _strip_copy_suffix(node_id: str) -> str:
    text = str(node_id or "")
    idx = text.find(_COPY_MARKER)
    return text[:idx] if idx != -1 else text


def _is_layout_artifact_node_id(*, node_id: str, node: NodeModel) -> bool:
    # 布局层可能插入：
    # - 局部变量 relay（node_localvar_relay_block_...）
    # - 数据节点副本（is_data_node_copy=True / *_copy_block_*）
    return _is_local_var_relay_node_id(node_id) or _is_data_node_copy(node) or (_COPY_MARKER in str(node_id or ""))


@dataclass(frozen=True, slots=True)
class ReverseGraphCodeOptions:
    """GraphModel -> Graph Code 的生成选项。"""

    scope: str = "server"  # "server" | "client"
    class_name: str = ""  # 默认使用 graph_name；为空时自动推导
    include_sys_path_bootstrap: bool = True
    include_validate_node_graph_in_init: bool = True
    include_main_validate_cli: bool = True


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
        lines.extend(_render_workspace_bootstrap_lines())
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
        )
        lines.append("")

    # ===== register_handlers =====
    lines.extend(_render_register_handlers_lines(model=model, event_ids=event_ids))
    lines.append("")

    if options.include_main_validate_cli:
        lines.extend(_render_main_validate_cli_lines())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_semantic_signature(model: GraphModel, *, wl_iterations: int = 4) -> Dict[str, Any]:
    """构造“忽略 node/edge id 与布局 pos 的语义签名”，用于 round-trip 比较。"""
    node_hashes = _compute_wl_node_hashes(model, iterations=wl_iterations)
    node_multiset: Dict[str, int] = {}
    for node_id, h in node_hashes.items():
        node_multiset[h] = node_multiset.get(h, 0) + 1

    edge_multiset: Dict[str, int] = {}
    for edge in (model.edges or {}).values():
        src_hash = node_hashes.get(edge.src_node, "<missing>")
        dst_hash = node_hashes.get(edge.dst_node, "<missing>")
        key = f"{src_hash}|{edge.src_port}=>{dst_hash}|{edge.dst_port}"
        edge_multiset[key] = edge_multiset.get(key, 0) + 1

    return {
        "graph_id": str(getattr(model, "graph_id", "") or ""),
        "graph_name": str(getattr(model, "graph_name", "") or ""),
        "description": str(getattr(model, "description", "") or ""),
        "graph_variables": _normalize_graph_variables(getattr(model, "graph_variables", []) or []),
        "metadata": _normalize_graph_metadata(getattr(model, "metadata", {}) or {}),
        "nodes": dict(sorted(node_multiset.items(), key=lambda item: item[0])),
        "edges": dict(sorted(edge_multiset.items(), key=lambda item: item[0])),
    }


def diff_semantic_signature(sig_a: Mapping[str, Any], sig_b: Mapping[str, Any]) -> List[str]:
    """对两个语义签名做差分，返回人类可读的差异信息列表。"""
    diffs: List[str] = []

    def _diff_field(field: str) -> None:
        if sig_a.get(field) != sig_b.get(field):
            diffs.append(f"{field} 不一致：A={sig_a.get(field)!r} B={sig_b.get(field)!r}")

    _diff_field("graph_id")
    _diff_field("graph_name")
    _diff_field("description")
    _diff_field("graph_variables")
    _diff_field("metadata")

    if sig_a.get("nodes") != sig_b.get("nodes"):
        diffs.append("节点集合（按结构哈希）不一致")
    if sig_a.get("edges") != sig_b.get("edges"):
        diffs.append("连线集合（按结构哈希）不一致")

    return diffs


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


def _render_workspace_bootstrap_lines() -> List[str]:
    return [
        "import sys",
        "from pathlib import Path",
        "",
        "PROJECT_ROOT = next(",
        "    p",
        "    for p in Path(__file__).resolve().parents",
        "    if (p / 'assets' / '资源库').is_dir() or ((p / 'engine').is_dir() and (p / 'app').is_dir())",
        ")",
        "sys.path.insert(0, str(PROJECT_ROOT))",
        "sys.path.insert(1, str(PROJECT_ROOT / 'assets'))",
    ]


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


def _render_node_call_args(
    *,
    node: NodeModel,
    node_def: NodeDef,
    node_library: Dict[str, NodeDef],
    data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
    var_mapping: Mapping[Tuple[str, str], str],
) -> List[str]:
    """渲染节点调用参数（不包含 self.game）。"""
    # 仅输出“有数据连线或有输入常量”的端口；缺省保持省略，以便 NodeDef.input_defaults 生效。
    provided: List[Tuple[str, str]] = []
    for port in (node.inputs or []):
        port_name = str(getattr(port, "name", "") or "")
        if not port_name:
            continue
        if is_flow_port_with_context(node, port_name, False, node_library):
            continue
        expr = None
        source = data_in_edge.get((node.id, port_name))
        if source is not None:
            expr = var_mapping.get((source[0], source[1]))
            if expr is None:
                raise ReverseGraphCodeError(
                    f"无法解析数据来源变量：{node.title}.{port_name} 来自 {source}"
                )
        elif port_name in (node.input_constants or {}):
            expr = format_constant((node.input_constants or {}).get(port_name))
        else:
            continue
        provided.append((port_name, expr))

    # 参数输出策略：
    # - 优先关键字参数（可读、避免跳位）；
    # - 若端口名不可作为 keyword，则尝试用位置参数（要求“从0开始连续提供”）。
    keyword_args: List[str] = []
    positional_args: List[str] = []

    provided_map = {k: v for k, v in provided}
    inputs_in_order = [str(x) for x in list(getattr(node_def, "inputs", []) or [])]

    def _is_kw(name: str) -> bool:
        return bool(name) and name.isidentifier() and (not keyword.iskeyword(name))

    # 若存在不可作为 keyword 的端口名，则必须转为 positional，并要求不跳位
    needs_positional = any((not _is_kw(name)) for name in provided_map.keys())
    if not needs_positional:
        for port_name in inputs_in_order:
            if port_name in provided_map:
                keyword_args.append(f"{port_name}={provided_map[port_name]}")
        # 对于动态输入端口（不在 NodeDef.inputs 中），按 node.inputs 顺序追加（稳定）
        for port_name, expr in provided:
            if port_name in inputs_in_order:
                continue
            keyword_args.append(f"{port_name}={expr}")
        return keyword_args

    # 情况 A：动态数字端口（典型：拼装列表/拼装字典等变参节点），NodeDef.inputs 仅含占位符，实际端口按位置生成
    non_kw_names = [name for name in provided_map.keys() if not _is_kw(name)]
    if non_kw_names and all(str(name).isdigit() for name in non_kw_names):
        numeric_ports = sorted({int(str(name)) for name in non_kw_names})
        if numeric_ports and numeric_ports[0] != 0:
            raise ReverseGraphCodeError(
                f"节点 {node.title} 的数字端口必须从 0 开始连续提供，但当前最小端口为 {numeric_ports[0]}"
            )
        for expected in range(0, (numeric_ports[-1] if numeric_ports else -1) + 1):
            key = str(expected)
            if key not in provided_map:
                raise ReverseGraphCodeError(
                    f"节点 {node.title} 的数字端口必须连续提供（缺少 {key!r}），无法生成位置参数"
                )
            positional_args.append(provided_map[key])

        # 其余（可关键字）端口按 NodeDef.inputs 顺序追加为 keyword，避免跳位
        for port_name in inputs_in_order:
            if port_name in provided_map and _is_kw(port_name):
                keyword_args.append(f"{port_name}={provided_map[port_name]}")
        for port_name, expr in provided:
            if port_name in inputs_in_order or port_name.isdigit():
                continue
            if not _is_kw(port_name):
                raise ReverseGraphCodeError(
                    f"节点 {node.title} 的动态端口名不可作为关键字参数：{port_name!r}"
                )
            keyword_args.append(f"{port_name}={expr}")
        return positional_args + keyword_args

    # 情况 B：静态端口中出现不可 keyword 的名称（极少见），尝试按 NodeDef.inputs 位置表达，且不允许跳位
    max_index = -1
    for idx, name in enumerate(inputs_in_order):
        if name in provided_map and (not _is_kw(name)):
            max_index = max(max_index, idx)
    if max_index < 0:
        raise ReverseGraphCodeError(
            f"节点 {node.title} 存在不可关键字参数的动态端口，且无法按位置参数表达"
        )

    for idx in range(0, max_index + 1):
        port_name = inputs_in_order[idx]
        if port_name not in provided_map:
            raise ReverseGraphCodeError(
                f"节点 {node.title} 需要以位置参数表达端口 {inputs_in_order[max_index]!r}，"
                f"但其前置端口 {port_name!r} 缺少数据来源/常量，无法不跳位生成"
            )
        positional_args.append(provided_map[port_name])

    for port_name in inputs_in_order[max_index + 1 :]:
        if port_name in provided_map:
            keyword_args.append(f"{port_name}={provided_map[port_name]}")

    # 动态端口：只能在 keyword 区域表达（若不可关键字则在上面已报错）
    for port_name, expr in provided:
        if port_name in inputs_in_order:
            continue
        if not _is_kw(port_name):
            raise ReverseGraphCodeError(
                f"节点 {node.title} 的动态端口名不可作为关键字参数：{port_name!r}"
            )
        keyword_args.append(f"{port_name}={expr}")

    return positional_args + keyword_args


class _StructuredEventEmitter:
    """按流程边结构化生成事件方法体（支持 if/match/for/break + 复合节点多流程出口 match）。"""

    def __init__(
        self,
        *,
        model: GraphModel,
        member_set: set[str],
        node_library: Dict[str, NodeDef],
        node_name_index: Dict[str, str],
        call_name_candidates_by_identity: Dict[int, List[str]],
        composite_alias_by_id: Dict[str, str],
    ) -> None:
        self.model = model
        self.member_set = set(member_set)
        self.node_library = node_library
        self.node_name_index = node_name_index
        self.call_name_candidates_by_identity = call_name_candidates_by_identity
        self.composite_alias_by_id = dict(composite_alias_by_id or {})
        self._composite_entry_method_name: str = "执行"

        # (dst_node, dst_port) -> (src_node, src_port)
        self.data_in_edge: Dict[Tuple[str, str], Tuple[str, str]] = {}
        # src_node -> [(src_port, dst_node, dst_port), ...]（仅流程边）
        self.flow_out: Dict[str, List[Tuple[str, str, str]]] = {}
        # (src_node, src_port) -> (dst_node, dst_port)
        self.flow_out_by_port: Dict[Tuple[str, str], Tuple[str, str]] = {}

        self._build_edge_indices()

        self.emitted_nodes: set[str] = set()

    def _is_flow_port(self, node: NodeModel, port_name: str, is_source: bool) -> bool:
        return is_flow_port_with_context(node, port_name, is_source, self.node_library)

    def _resolve_data_source(
        self,
        src_node_id: str,
        src_port: str,
        *,
        raw_data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
        depth: int = 0,
    ) -> Tuple[str, str]:
        """对 data edge 的源端做归一化：
        - data copy 节点 → canonical original id
        - localvar relay 节点（node_localvar_relay_block_*）的 `值` 输出 → 透传其 `初始值` 上游来源
        """
        if depth > 50:
            return str(src_node_id), str(src_port)

        src_id = str(src_node_id)
        port = str(src_port)
        node = self.model.nodes.get(src_id)
        if node is not None:
            if _is_data_node_copy(node) or (_COPY_MARKER in src_id):
                candidate = str(getattr(node, "original_node_id", "") or "") or src_id
                canonical = _strip_copy_suffix(candidate)
                if canonical and canonical != src_id:
                    return self._resolve_data_source(
                        canonical,
                        port,
                        raw_data_in_edge=raw_data_in_edge,
                        depth=depth + 1,
                    )

        if _is_local_var_relay_node_id(src_id) and port == "值":
            upstream = raw_data_in_edge.get((src_id, "初始值"))
            if upstream is not None:
                return self._resolve_data_source(
                    upstream[0],
                    upstream[1],
                    raw_data_in_edge=raw_data_in_edge,
                    depth=depth + 1,
                )

        return src_id, port

    def _build_edge_indices(self) -> None:
        raw_data_in_edge: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for edge in (getattr(self.model, "edges", None) or {}).values():
            if edge.dst_node not in self.member_set:
                continue
            if edge.src_node not in self.member_set:
                continue
            dst_node = self.model.nodes.get(edge.dst_node)
            src_node = self.model.nodes.get(edge.src_node)
            if dst_node is None or src_node is None:
                continue

            src_is_flow = self._is_flow_port(src_node, str(edge.src_port), True)
            dst_is_flow = self._is_flow_port(dst_node, str(edge.dst_port), False)

            if src_is_flow and dst_is_flow:
                self.flow_out.setdefault(edge.src_node, []).append(
                    (str(edge.src_port), str(edge.dst_node), str(edge.dst_port))
                )
                key = (str(edge.src_node), str(edge.src_port))
                if key in self.flow_out_by_port:
                    raise ReverseGraphCodeError(
                        f"同一流程输出端口存在多条流程连线：{src_node.title}.{edge.src_port}"
                    )
                self.flow_out_by_port[key] = (str(edge.dst_node), str(edge.dst_port))
                continue

            if (not src_is_flow) and (not dst_is_flow):
                key2 = (str(edge.dst_node), str(edge.dst_port))
                if key2 in raw_data_in_edge:
                    raise ReverseGraphCodeError(
                        f"输入端口存在多条数据连线：{dst_node.title}.{edge.dst_port}"
                    )
                raw_data_in_edge[key2] = (str(edge.src_node), str(edge.src_port))

        # 归一化 data_in_edge：剔除 layout relay / data copy 的影响（避免反向生成把布局结构写成真实语义节点）
        for (dst_node_id, dst_port), (src_node_id, src_port) in raw_data_in_edge.items():
            resolved_src = self._resolve_data_source(
                str(src_node_id),
                str(src_port),
                raw_data_in_edge=raw_data_in_edge,
            )
            self.data_in_edge[(str(dst_node_id), str(dst_port))] = resolved_src

    def emit_event_body(
        self,
        *,
        out_lines: List[str],
        event_node: NodeModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> Optional[str]:
        visited_flow: set[str] = set()

        # 事件主入口：event.流程出 -> ...
        entry = self.flow_out_by_port.get((str(event_node.id), "流程出"))
        if entry is not None:
            start_node, start_port = entry
            if start_port == "跳出循环":
                raise ReverseGraphCodeError("事件入口不应直接连到循环的跳出循环端口")
            self._emit_flow_sequence(
                out_lines=out_lines,
                start_node_id=start_node,
                stop_node_id=None,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=[],
                visited_flow=visited_flow,
            )

        # 额外流程入口：
        # 有些图（尤其是 client 校准/布局图）会在同一事件方法内放置“无流程入”的流程入口节点，
        # 它们与事件主入口不连通，但仍属于图的一部分。这里按 member_set 扫描并补发这些入口序列。
        def _is_flow_entry_node(node: NodeModel) -> bool:
            has_flow_out = any(
                (str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), True))
                for p in (getattr(node, "outputs", None) or [])
            )
            has_flow_in = any(
                (str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), False))
                for p in (getattr(node, "inputs", None) or [])
            )
            return bool(has_flow_out and (not has_flow_in))

        extra_roots: List[str] = []
        for node_id in sorted(self.member_set):
            if str(node_id) == str(getattr(event_node, "id", "") or ""):
                continue
            if node_id in self.emitted_nodes:
                continue
            node = self.model.nodes.get(str(node_id))
            if node is None:
                continue
            if str(getattr(node, "category", "") or "") == "事件节点":
                continue
            if _is_flow_entry_node(node):
                extra_roots.append(str(node_id))

        for root_id in extra_roots:
            self._emit_flow_sequence(
                out_lines=out_lines,
                start_node_id=root_id,
                stop_node_id=None,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=[],
                visited_flow=visited_flow,
            )

        # client 过滤器节点图：return <值> 会被解析为 graph_end（节点图结束）节点。
        # 对这种“无流程、纯数据链”的图，需要在这里补发数据节点，并将返回表达式交给上层写入 `return <expr>`。
        graph_end_nodes: List[NodeModel] = []
        for nid in self.member_set:
            node = self.model.nodes.get(str(nid))
            if node is None:
                continue
            if _is_layout_artifact_node_id(node_id=str(nid), node=node):
                continue
            if str(getattr(node, "id", "") or "").startswith("graph_end_"):
                graph_end_nodes.append(node)
                continue
            if str(getattr(node, "title", "") or "").strip().startswith("节点图结束"):
                graph_end_nodes.append(node)

        return_expr: Optional[str] = None
        if graph_end_nodes:
            if len(graph_end_nodes) > 1:
                raise ReverseGraphCodeError(
                    "同一事件内存在多个节点图结束（graph_end）节点，无法稳定反向生成 return："
                    + ", ".join(str(getattr(n, "id", "") or "") for n in graph_end_nodes[:5])
                    + ("..." if len(graph_end_nodes) > 5 else "")
                )
            end_node = graph_end_nodes[0]
            expr = self._expr_for_optional_data_input(
                node_id=str(end_node.id),
                port_name="结果",
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                out_lines=out_lines,
                indent=indent,
                loop_stack=[],
            )
            if not str(expr or "").strip():
                raise ReverseGraphCodeError("节点图结束（graph_end）缺少结果数据来源，无法生成 return 表达式")
            return_expr = str(expr)

        # 覆盖性校验：事件 member_set 内除了事件节点自身与布局产物外，不应再有无法发出的节点
        remaining: List[str] = []
        for nid in self.member_set:
            nid_str = str(nid)
            if nid_str == str(getattr(event_node, "id", "") or ""):
                continue
            if nid_str.startswith("graph_end_"):
                continue
            if nid_str in self.emitted_nodes:
                continue
            node = self.model.nodes.get(nid_str)
            if node is None:
                continue
            if _is_layout_artifact_node_id(node_id=nid_str, node=node):
                continue
            if str(getattr(node, "title", "") or "").strip().startswith("节点图结束"):
                continue
            remaining.append(nid_str)

        if remaining:
            node = self.model.nodes.get(remaining[0])
            title = f"{getattr(node, 'category', '')}/{getattr(node, 'title', '')}" if node is not None else "<missing>"
            raise ReverseGraphCodeError(
                "事件内存在无法稳定反向生成的节点（可能是无流程入但也非流程入口，或存在多入口 join 等结构）："
                + f"{remaining[0]} ({title})"
            )

        return return_expr

    def _emit_flow_sequence(
        self,
        *,
        out_lines: List[str],
        start_node_id: Optional[str],
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> None:
        current = str(start_node_id) if start_node_id else ""
        while current and current != str(stop_node_id or ""):
            if current in visited_flow:
                # 防止意外环路导致死循环（结构化图不应出现此情况）
                return
            visited_flow.add(current)

            node = self.model.nodes.get(current)
            if node is None:
                return

            title = str(getattr(node, "title", "") or "").strip()
            category = str(getattr(node, "category", "") or "").strip()

            # 控制流：双分支 if/else
            if title == "双分支":
                true_target = self._flow_target(current, "是")
                false_target = self._flow_target(current, "否")
                # 若该双分支节点未连接任何分支出口，则其仅作为“流程控制节点/双分支”普通节点存在（常见于校准/布局图）。
                # 此时不能用 `if ...:` 语法表达（解析器无法从常量/复杂表达式稳定抽取条件变量），应退化为普通节点调用。
                if true_target is None and false_target is None:
                    self._emit_node_statement(
                        out_lines=out_lines,
                        node_id=current,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent,
                    )
                    next_flow = self._pick_single_flow_successor(current)
                    if next_flow is None:
                        return
                    next_node, next_port = next_flow
                    if next_port == "跳出循环":
                        if not loop_stack:
                            raise ReverseGraphCodeError("发现跳出循环连线，但当前不在循环体内")
                        if next_node != loop_stack[-1]:
                            raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                        out_lines.append(f"{indent}break")
                        return
                    current = next_node
                    continue

                # 结构化 if 已在源码中体现该节点语义：标记为已发出，避免后续覆盖性校验误判“遗漏节点”
                self.emitted_nodes.add(str(current))
                join = self._find_join_for_branches(
                    branch_starts=[true_target, false_target],
                    stop_node_id=stop_node_id,
                )

                # 允许“部分分支接续到外层 stop_node_id”的结构（与多分支 match 的兜底逻辑一致）：
                # - 外层 control-flow（例如循环/更外层 if）可能传入 stop_node_id 作为本 block 的终止边界；
                # - 若当前 if 的某一侧分支可达 stop_node_id、另一侧不可达，则不存在“至少两侧可达”的 join，
                #   但仍需要让可达侧继续向后生成，并在不可达侧末尾注入 return 防止错误接续。
                if (not join) and stop_node_id:
                    stop = str(stop_node_id)
                    for target in (true_target, false_target):
                        if target is None:
                            continue
                        node_id, dst_port = target
                        if dst_port == "跳出循环":
                            continue
                        if node_id and self._can_reach(str(node_id), stop):
                            join = stop
                            break

                # 关键点：若两条分支的流程节点共同依赖某些“纯数据节点”，必须把这些数据节点提升到 if 之前，
                # 否则解析器在分支体 snapshot/restore 下会出现“另一分支看不到变量映射”的缺线。
                self._emit_shared_data_sources_for_branches(
                    out_lines=out_lines,
                    indent=indent,
                    branch_targets=[true_target, false_target],
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                )
                cond_expr = self._expr_for_required_data_input(
                    node_id=current,
                    port_name="条件",
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    out_lines=out_lines,
                    indent=indent,
                    loop_stack=loop_stack,
                )

                out_lines.append(f"{indent}if {cond_expr}:")
                self._emit_branch_body(
                    out_lines=out_lines,
                    branch_target=true_target,
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent + "    ",
                    loop_stack=loop_stack,
                    visited_flow=set(visited_flow),
                )
                out_lines.append(f"{indent}else:")
                self._emit_branch_body(
                    out_lines=out_lines,
                    branch_target=false_target,
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent + "    ",
                    loop_stack=loop_stack,
                    visited_flow=set(visited_flow),
                )

                # 有共享 tail 才能继续向后生成，否则整个 if 结构已覆盖剩余流程
                if join:
                    current = join
                    continue
                return

            # 控制流：多分支 match/case
            if title == "多分支":
                # 若多分支节点没有任何流程出口连线，则其仅作为普通节点存在（常见于校准/布局图），退化为普通节点调用。
                has_any_branch_edge = bool(self.flow_out.get(str(current), []) or [])
                if not has_any_branch_edge:
                    self._emit_node_statement(
                        out_lines=out_lines,
                        node_id=current,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent,
                    )
                    next_flow = self._pick_single_flow_successor(current)
                    if next_flow is None:
                        return
                    next_node, next_port = next_flow
                    if next_port == "跳出循环":
                        if not loop_stack:
                            raise ReverseGraphCodeError("发现跳出循环连线，但当前不在循环体内")
                        if next_node != loop_stack[-1]:
                            raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                        out_lines.append(f"{indent}break")
                        return
                    current = next_node
                    continue

                # 结构化 match 已在源码中体现该节点语义：标记为已发出，避免后续覆盖性校验误判“遗漏节点”
                self.emitted_nodes.add(str(current))
                control_expr = self._expr_for_required_match_subject(
                    node_id=current,
                    port_name="控制表达式",
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    out_lines=out_lines,
                    indent=indent,
                    loop_stack=loop_stack,
                )

                # 分支端口（流程输出）：包含默认 + 动态 case
                flow_out_ports = [
                    str(getattr(p, "name", "") or "")
                    for p in (getattr(node, "outputs", None) or [])
                    if str(getattr(p, "name", "") or "")
                ]
                if not flow_out_ports:
                    raise ReverseGraphCodeError("多分支节点缺少输出端口")

                branch_targets = [self._flow_target(current, port) for port in flow_out_ports]
                join = self._find_join_for_branches(branch_starts=branch_targets, stop_node_id=stop_node_id)

                # 允许“部分分支接续到外层 stop_node_id”的结构：
                # - 对于嵌套控制流（例如 if 分支内的 match），外层会给当前 block 传入 stop_node_id；
                # - 若 match 的部分 case 能到达 stop_node_id、但并非所有 case 都能到达，则 _find_join_for_branches
                #   会返回 None（因为不存在“至少两个分支共同可达”的 join）；
                # - 这种图在 AST 中应表达为：无法到达 join 的 case 末尾显式 `return`，其余 case 继续向后执行。
                # 因此这里将 stop_node_id 作为“弱 join”兜底：让可达分支继续向后，且让不可达分支被 _emit_branch_body 注入 return。
                if (not join) and stop_node_id:
                    stop = str(stop_node_id)
                    for target in branch_targets:
                        if target is None:
                            continue
                        node_id, dst_port = target
                        if dst_port == "跳出循环":
                            continue
                        if node_id and self._can_reach(str(node_id), stop):
                            join = stop
                            break

                self._emit_shared_data_sources_for_branches(
                    out_lines=out_lines,
                    indent=indent,
                    branch_targets=branch_targets,
                    join_node_id=join,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                )

                out_lines.append(f"{indent}match {control_expr}:")
                # case 输出顺序：
                # - 对于“嵌套控制流 + 外层 join”的图，IR 在外层 if/match 的出口推断中会使用“分支体最后一个流程节点”作为接续点；
                #   因此这里需要保证“能接续到 join 的分支”在源码中尽量靠后，避免错误地把不可达分支当作接续点。
                # - 若 join 存在：将可达 join 的 case 放在后面；不可达的 case 放在前面。
                ordered_ports = list(flow_out_ports)
                if join:
                    join_id = str(join)
                    reachable_ports: List[str] = []
                    unreachable_ports: List[str] = []
                    for port_name in ordered_ports:
                        target = self._flow_target(current, port_name)
                        if target is None or target[1] == "跳出循环":
                            unreachable_ports.append(port_name)
                            continue
                        start_id = str(target[0])
                        if start_id == join_id or self._can_reach(start_id, join_id):
                            reachable_ports.append(port_name)
                        else:
                            unreachable_ports.append(port_name)
                    ordered_ports = unreachable_ports + reachable_ports

                for port_name in ordered_ports:
                    pattern = self._render_match_case_pattern(port_name)
                    out_lines.append(f"{indent}    case {pattern}:")
                    self._emit_branch_body(
                        out_lines=out_lines,
                        branch_target=self._flow_target(current, port_name),
                        join_node_id=join,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent + "        ",
                        loop_stack=loop_stack,
                        visited_flow=set(visited_flow),
                    )

                if join:
                    current = join
                    continue
                return

            # 控制流：复合节点多流程出口（match self.<复合实例>.<入口>(...)）
            #
            # 对齐正向解析协议：`engine.graph.ir.statement_flow_builder.handle_match_over_composite_call`
            # - match subject 必须为 `self.<alias>.<method>(...)`
            # - case 使用字符串字面量（流程出口名）或 `_`（仅当存在“默认”出口时）
            node_def = _try_resolve_node_def(node=node, node_library=self.node_library)
            if node_def is not None and bool(getattr(node_def, "is_composite", False)):
                flow_outputs_in_order = [
                    str(getattr(p, "name", "") or "")
                    for p in (getattr(node, "outputs", None) or [])
                    if str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), True)
                ]
                connected_flow_outputs = [
                    name for name in flow_outputs_in_order if self._flow_target(current, name) is not None
                ]
                needs_match = False
                if len(connected_flow_outputs) > 1:
                    needs_match = True
                elif (
                    len(connected_flow_outputs) == 1
                    and len(flow_outputs_in_order) > 1
                    and connected_flow_outputs[0] != flow_outputs_in_order[0]
                ):
                    # 仅连接了一个“非默认（非首个）”流程出口：必须用 match 显式指定出口，
                    # 否则解析器会用默认出口自动接续，导致 src_port 语义不一致。
                    needs_match = True

                if needs_match:
                    # 复合节点的 match 语法无法表达其“数据输出”的变量绑定；
                    # 若该复合节点的任一数据输出被下游节点引用，则当前图无法稳定反向（fail-closed）。
                    for (_dst_node, _dst_port), (src_node_id, src_port) in list(self.data_in_edge.items()):
                        if str(src_node_id) != str(current):
                            continue
                        if not self._is_flow_port(node, str(src_port), True):
                            raise ReverseGraphCodeError(
                                f"复合节点 {node.title} 的数据输出端口 {src_port!r} 被下游引用，但该节点又存在多流程出口；"
                                "当前版本无法同时表达“多流程出口 + 数据输出”语义，请拆分图结构或减少对该数据输出的依赖。"
                            )

                    # 先确保复合节点调用所需的数据来源节点已被发出（仅允许纯数据节点在此处被提前发出）
                    for port in (getattr(node, "inputs", None) or []):
                        pname = str(getattr(port, "name", "") or "")
                        if not pname or self._is_flow_port(node, pname, False):
                            continue
                        source = self.data_in_edge.get((str(node.id), pname))
                        if source is None:
                            continue
                        src_node_id, _src_port = source
                        if src_node_id not in self.emitted_nodes:
                            self._ensure_data_node_emitted(
                                out_lines=out_lines,
                                node_id=src_node_id,
                                var_mapping=var_mapping,
                                used_var_names=used_var_names,
                                indent=indent,
                            )

                    # match subject：self.<复合实例>.<入口>(...)
                    composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(
                        getattr(node, "composite_id", "") or ""
                    ).strip()
                    if not composite_id:
                        composite_id = str(getattr(node_def, "name", "") or getattr(node, "title", "") or "").strip()
                    alias = self.composite_alias_by_id.get(composite_id) or (
                        make_valid_identifier(str(getattr(node_def, "name", "") or getattr(node, "title", "") or "")) or "复合实例"
                    )
                    if not alias.isidentifier() or keyword.iskeyword(alias):
                        raise ReverseGraphCodeError(f"复合节点实例名不可作为 self 属性：{alias!r}")

                    call_args = _render_node_call_args(
                        node=node,
                        node_def=node_def,
                        node_library=self.node_library,
                        data_in_edge=self.data_in_edge,
                        var_mapping=var_mapping,
                    )
                    if call_args:
                        subject_expr = f"self.{alias}.{self._composite_entry_method_name}({', '.join(call_args)})"
                    else:
                        subject_expr = f"self.{alias}.{self._composite_entry_method_name}()"

                    branch_targets = [self._flow_target(current, port) for port in connected_flow_outputs]
                    join = self._find_join_for_branches(branch_starts=branch_targets, stop_node_id=stop_node_id)

                    self._emit_shared_data_sources_for_branches(
                        out_lines=out_lines,
                        indent=indent,
                        branch_targets=branch_targets,
                        join_node_id=join,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                    )

                    out_lines.append(f"{indent}match {subject_expr}:")
                    for port_name in connected_flow_outputs:
                        pattern = "_" if port_name == "默认" else repr(port_name)
                        out_lines.append(f"{indent}    case {pattern}:")
                        self._emit_branch_body(
                            out_lines=out_lines,
                            branch_target=self._flow_target(current, port_name),
                            join_node_id=join,
                            var_mapping=var_mapping,
                            used_var_names=used_var_names,
                            indent=indent + "        ",
                            loop_stack=loop_stack,
                            visited_flow=set(visited_flow),
                        )

                    self.emitted_nodes.add(str(current))
                    if join:
                        current = join
                        continue
                    return

            # 控制流：for 循环（有限循环 / 列表迭代循环）
            if title in LOOP_NODE_NAMES:
                # 循环前提升：若循环后的流程节点依赖某些“纯数据节点”，这些节点必须在循环外定义，
                # 否则 IR 解析在 loop 的 snapshot/restore 下会丢失变量映射，导致循环后缺线。
                next_target_preview = self._flow_target(current, "循环完成")
                if next_target_preview is not None and next_target_preview[1] != "跳出循环":
                    after_region = self._collect_flow_nodes_in_region(
                        start_node_id=next_target_preview[0],
                        stop_node_id=stop_node_id,
                    )
                    after_sources = self._collect_direct_data_sources_into_nodes(after_region)
                    for src_id in sorted(after_sources):
                        if src_id in self.emitted_nodes:
                            continue
                        src_node = self.model.nodes.get(src_id)
                        if src_node is None:
                            continue
                        if self._node_has_any_flow_port(src_node):
                            continue
                        if not self._can_emit_data_node_without_unbound_flow_sources(
                            node_id=str(src_id),
                            var_mapping=var_mapping,
                            visiting=set(),
                        ):
                            continue
                        self._ensure_data_node_emitted(
                            out_lines=out_lines,
                            node_id=src_id,
                            var_mapping=var_mapping,
                            used_var_names=used_var_names,
                            indent=indent,
                        )

                if title == "有限循环":
                    loop_var = self._unique_var_name("当前循环值", used_var_names)
                    var_mapping[(current, "当前循环值")] = loop_var
                    start_expr = self._expr_for_optional_data_input(
                        node_id=current,
                        port_name="循环起始值",
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        out_lines=out_lines,
                        indent=indent,
                        loop_stack=loop_stack,
                    )
                    end_expr = self._expr_for_optional_data_input(
                        node_id=current,
                        port_name="循环终止值",
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        out_lines=out_lines,
                        indent=indent,
                        loop_stack=loop_stack,
                    )
                    if not end_expr:
                        raise ReverseGraphCodeError("有限循环缺少 循环终止值（必须有数据来源或常量）")
                    if start_expr and start_expr != "0":
                        range_expr = f"range({start_expr}, {end_expr})"
                    else:
                        range_expr = f"range({end_expr})"
                    out_lines.append(f"{indent}for {loop_var} in {range_expr}:")
                else:
                    # 列表迭代循环：迭代列表必须为变量名（Name），否则正向解析不会连边
                    loop_var = self._unique_var_name("迭代值", used_var_names)
                    var_mapping[(current, "迭代值")] = loop_var
                    iter_expr = self._expr_for_required_match_subject(
                        node_id=current,
                        port_name="迭代列表",
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        out_lines=out_lines,
                        indent=indent,
                        loop_stack=loop_stack,
                    )
                    out_lines.append(f"{indent}for {loop_var} in {iter_expr}:")

                # 循环节点本身是控制流结构，不会通过 `_emit_node_statement` 生成；
                # 但其数据输出（当前循环值/迭代值）会被循环体内节点引用。
                # 这里将其视为“已发出”，避免下游在解析数据来源时误判为“需要提前生成流程节点”。
                self.emitted_nodes.add(str(current))

                body_target = self._flow_target(current, "循环体")
                if body_target is None:
                    out_lines.append(f"{indent}    pass")
                elif body_target[1] == "跳出循环":
                    raise ReverseGraphCodeError("循环体出口不应直接连到跳出循环端口")
                else:
                    self._emit_flow_sequence(
                        out_lines=out_lines,
                        start_node_id=body_target[0],
                        stop_node_id=None,
                        var_mapping=var_mapping,
                        used_var_names=used_var_names,
                        indent=indent + "    ",
                        loop_stack=loop_stack + [current],
                        visited_flow=set(),
                    )

                # 循环后续：从 循环完成 出口继续
                next_target = self._flow_target(current, "循环完成")
                if next_target is None:
                    return
                if next_target[1] == "跳出循环":
                    raise ReverseGraphCodeError("循环完成出口不应连到跳出循环端口")
                current = next_target[0]
                continue

            # 普通节点：按调用生成
            self._emit_node_statement(
                out_lines=out_lines,
                node_id=current,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
            )

            next_flow = self._pick_single_flow_successor(current)
            if next_flow is None:
                return
            next_node, next_port = next_flow
            if next_port == "跳出循环":
                # break：仅当处于循环体内且目标为当前循环节点时才合法
                if not loop_stack:
                    raise ReverseGraphCodeError("发现跳出循环连线，但当前不在循环体内")
                if next_node != loop_stack[-1]:
                    raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")
                out_lines.append(f"{indent}break")
                return
            current = next_node

    def _emit_branch_body(
        self,
        *,
        out_lines: List[str],
        branch_target: Optional[Tuple[str, str]],
        join_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> None:
        # break-only 分支：直接连接到循环节点的“跳出循环”
        if branch_target is not None and branch_target[1] == "跳出循环":
            if not loop_stack or branch_target[0] != loop_stack[-1]:
                raise ReverseGraphCodeError("break 分支不在正确的循环上下文内")
            out_lines.append(f"{indent}break")
            return

        if branch_target is None or (join_node_id and branch_target[0] == join_node_id):
            out_lines.append(f"{indent}pass")
            return

        self._emit_flow_sequence(
            out_lines=out_lines,
            start_node_id=branch_target[0],
            stop_node_id=join_node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=loop_stack,
            visited_flow=visited_flow,
        )

        # 若 join 存在但该分支不通向 join，则必须显式 return 以避免解析器自动接续
        if join_node_id and (not self._can_reach(branch_target[0], join_node_id)):
            out_lines.append(f"{indent}return")

    def _emit_shared_data_sources_for_branches(
        self,
        *,
        out_lines: List[str],
        indent: str,
        branch_targets: List[Optional[Tuple[str, str]]],
        join_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
    ) -> None:
        """将被多个分支共同依赖的“纯数据节点”提升到控制流语句之前。"""
        branch_flow_nodes: List[set[str]] = []
        for target in branch_targets:
            if target is None:
                branch_flow_nodes.append(set())
                continue
            node_id, dst_port = target
            if dst_port == "跳出循环":
                branch_flow_nodes.append(set())
                continue
            branch_flow_nodes.append(
                self._collect_flow_nodes_in_region(start_node_id=node_id, stop_node_id=join_node_id)
            )

        # 统计每个“数据来源节点”在多少个分支中被使用（只看直接连到分支内流程节点的数据边）
        src_count: Dict[str, int] = {}
        for flow_nodes in branch_flow_nodes:
            srcs = self._collect_direct_data_sources_into_nodes(flow_nodes)
            for src in srcs:
                src_count[src] = src_count.get(src, 0) + 1

        shared_sources = [node_id for node_id, count in src_count.items() if count >= 2]
        # join 节点本身的“纯数据来源”也必须在控制流语句前被绑定，
        # 否则可能出现“仅在某个分支内首次发出该数据节点 -> join 后使用时缺少数据来源”的严格解析失败。
        join_sources: set[str] = set()
        if join_node_id:
            join_sources = self._collect_direct_data_sources_into_nodes({str(join_node_id)})

        lifted_sources = set(shared_sources) | set(join_sources)
        # 稳定输出顺序：按 node_id 排序（避免 diff 噪音）
        for node_id in sorted(lifted_sources):
            if node_id in self.emitted_nodes:
                continue
            if not self._can_emit_data_node_without_unbound_flow_sources(
                node_id=str(node_id),
                var_mapping=var_mapping,
                visiting=set(),
            ):
                continue
            self._ensure_data_node_emitted(
                out_lines=out_lines,
                node_id=node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
            )

    def _collect_flow_nodes_in_region(self, *, start_node_id: str, stop_node_id: Optional[str]) -> set[str]:
        """收集从 start 出发沿流程边可达、且在 stop 之前的流程节点集合。"""
        visited: set[str] = set()
        q = deque([str(start_node_id)])
        stop = str(stop_node_id) if stop_node_id else ""
        while q:
            node_id = q.popleft()
            if not node_id or node_id in visited:
                continue
            if stop and node_id == stop:
                continue
            visited.add(node_id)
            for _src_port, dst_node, dst_port in self.flow_out.get(node_id, []) or []:
                if dst_port == "跳出循环":
                    continue
                if dst_node not in self.member_set:
                    continue
                q.append(dst_node)
        return visited

    def _collect_direct_data_sources_into_nodes(self, nodes: set[str]) -> set[str]:
        """返回所有“直接连到这些节点任一数据输入端口”的来源节点集合（不做传递闭包）。"""
        result: set[str] = set()
        for dst_id in nodes:
            dst_node = self.model.nodes.get(dst_id)
            if dst_node is None:
                continue
            for port in (dst_node.inputs or []):
                pname = str(getattr(port, "name", "") or "")
                if not pname:
                    continue
                if self._is_flow_port(dst_node, pname, False):
                    continue
                source = self.data_in_edge.get((dst_id, pname))
                if source is None:
                    continue
                result.add(source[0])
        return result

    def _node_has_any_flow_port(self, node: NodeModel) -> bool:
        for port in (getattr(node, "outputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if pname and self._is_flow_port(node, pname, True):
                return True
        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if pname and self._is_flow_port(node, pname, False):
                return True
        return False

    def _can_emit_data_node_without_unbound_flow_sources(
        self,
        *,
        node_id: str,
        var_mapping: Mapping[Tuple[str, str], str],
        visiting: set[str],
    ) -> bool:
        """判断一个“纯数据节点”能否在当前作用域被提前发出（不依赖未绑定的流程节点输出）。"""
        nid = str(node_id or "")
        if not nid:
            return False
        if nid in visiting:
            return True
        visiting.add(nid)

        node = self.model.nodes.get(nid)
        if node is None:
            return False
        if self._node_has_any_flow_port(node):
            return False

        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname:
                continue
            if self._is_flow_port(node, pname, False):
                continue
            source = self.data_in_edge.get((nid, pname))
            if source is None:
                continue
            src_node_id, src_port = source
            src_key = (str(src_node_id), str(src_port))
            if src_key in var_mapping:
                continue
            src_node = self.model.nodes.get(src_key[0])
            if src_node is None:
                return False
            if self._node_has_any_flow_port(src_node):
                return False
            if not self._can_emit_data_node_without_unbound_flow_sources(
                node_id=src_key[0],
                var_mapping=var_mapping,
                visiting=visiting,
            ):
                return False

        return True

    def _emit_node_statement(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        if node_id in self.emitted_nodes:
            return
        node = self.model.nodes.get(node_id)
        if node is None:
            return

        node_def = _resolve_node_def(node=node, node_library=self.node_library)
        call_name = _pick_call_name_for_node(
            node=node,
            node_def=node_def,
            node_library=self.node_library,
            node_name_index=self.node_name_index,
            call_name_candidates_by_identity=self.call_name_candidates_by_identity,
        )

        # 先确保所有数据输入的来源节点已被发出（仅允许纯数据节点在此处被提前发出）
        for port in (node.inputs or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname:
                continue
            if self._is_flow_port(node, pname, False):
                continue
            source = self.data_in_edge.get((node_id, pname))
            if source is None:
                continue
            src_node_id, src_port = source
            src_key = (str(src_node_id), str(src_port))
            # 事件参数 / 已有映射：不需要也不允许“提前发出”源节点
            if src_key in var_mapping:
                continue
            if str(src_node_id) not in self.emitted_nodes:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=str(src_node_id),
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )

        data_outputs = [
            p
            for p in (node.outputs or [])
            if (str(getattr(p, "name", "") or "")) and (not self._is_flow_port(node, str(getattr(p, "name", "") or ""), True))
        ]
        output_var_names: List[str] = []
        if data_outputs:
            raw_names = [str(getattr(p, "name", "") or "") for p in data_outputs]
            # 动态输出端口（NodeDef.output_types 为空）：
            # 解析器会把“赋值目标变量名”当作输出端口名生成动态端口；
            # 因此必须使用端口名本身作为变量名，避免由于去重/改名导致 round-trip 端口集合变化。
            is_dynamic_outputs = bool(node_def is not None and (not getattr(node_def, "output_types", None)))
            output_var_names = raw_names if is_dynamic_outputs else _finalize_output_var_names(raw_names, used=used_var_names)
            for port, var_name in zip(data_outputs, output_var_names):
                port_name = str(getattr(port, "name", "") or "")
                var_mapping[(node.id, port_name)] = var_name

        extra_args = _render_node_call_args(
            node=node,
            node_def=node_def,
            node_library=self.node_library,
            data_in_edge=self.data_in_edge,
            var_mapping=var_mapping,
        )
        if bool(getattr(node_def, "is_composite", False)):
            composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(
                getattr(node, "composite_id", "") or ""
            ).strip()
            if not composite_id:
                composite_id = str(getattr(node_def, "name", "") or getattr(node, "title", "") or "").strip()
            alias = self.composite_alias_by_id.get(composite_id) or (
                make_valid_identifier(str(getattr(node_def, "name", "") or getattr(node, "title", "") or "")) or "复合实例"
            )
            if not alias.isidentifier() or keyword.iskeyword(alias):
                raise ReverseGraphCodeError(f"复合节点实例名不可作为 self 属性：{alias!r}")
            if extra_args:
                call_expr = f"self.{alias}.{self._composite_entry_method_name}({', '.join(extra_args)})"
            else:
                call_expr = f"self.{alias}.{self._composite_entry_method_name}()"
        else:
            call_expr = f"{call_name}({', '.join(['self.game'] + extra_args)})"

        if output_var_names:
            if len(output_var_names) == 1:
                out_lines.append(f"{indent}{output_var_names[0]} = {call_expr}")
            else:
                lhs = ", ".join(output_var_names)
                out_lines.append(f"{indent}{lhs} = {call_expr}")
        else:
            out_lines.append(f"{indent}{call_expr}")

        self.emitted_nodes.add(node_id)

    def _ensure_data_node_emitted(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        if node_id in self.emitted_nodes:
            return
        node = self.model.nodes.get(node_id)
        if node is None:
            return

        # 只允许纯数据节点被“提前发出”，避免破坏流程结构
        if any(self._is_flow_port(node, str(getattr(p, "name", "") or ""), True) for p in (node.outputs or [])) or any(
            self._is_flow_port(node, str(getattr(p, "name", "") or ""), False) for p in (node.inputs or [])
        ):
            raise ReverseGraphCodeError(
                f"数据依赖要求提前生成流程节点：{node.category}/{node.title}；该图在当前策略下无法稳定反向"
            )

        self._emit_node_statement(
            out_lines=out_lines,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )

    def _flow_target(self, src_node_id: str, src_port: str) -> Optional[Tuple[str, str]]:
        return self.flow_out_by_port.get((str(src_node_id), str(src_port)))

    def _pick_single_flow_successor(self, node_id: str) -> Optional[Tuple[str, str]]:
        outs = list(self.flow_out.get(str(node_id), []) or [])
        if not outs:
            return None
        if len(outs) != 1:
            node = self.model.nodes.get(node_id)
            title = getattr(node, "title", "") if node is not None else node_id
            raise ReverseGraphCodeError(f"节点存在多条流程出边但不是结构化控制流节点：{title}")
        _src_port, dst_node, dst_port = outs[0]
        return dst_node, dst_port

    def _can_reach(self, start: str, target: str) -> bool:
        return target in self._bfs_distances(start)

    def _bfs_distances(self, start: str) -> Dict[str, int]:
        start_id = str(start)
        dist: Dict[str, int] = {}
        q = deque([(start_id, 0)])
        while q:
            node_id, d = q.popleft()
            if node_id in dist:
                continue
            dist[node_id] = d
            for _src_port, dst_node, dst_port in self.flow_out.get(node_id, []) or []:
                # break 视为终止：不把“跳出循环”当作可继续的后继
                if dst_port == "跳出循环":
                    continue
                if dst_node not in self.member_set:
                    continue
                q.append((dst_node, d + 1))
        return dist

    def _find_join_for_branches(
        self,
        *,
        branch_starts: List[Optional[Tuple[str, str]]],
        stop_node_id: Optional[str],
    ) -> Optional[str]:
        # 收集“可继续”的起点：排除 break 与 None
        starts: List[str] = []
        for item in branch_starts:
            if item is None:
                continue
            node_id, dst_port = item
            if dst_port == "跳出循环":
                continue
            if stop_node_id and node_id == stop_node_id:
                continue
            starts.append(str(node_id))
        if len(starts) < 2:
            return None

        dist_maps = [self._bfs_distances(s) for s in starts]
        reach_count: Dict[str, int] = {}
        for dm in dist_maps:
            for node_id in dm.keys():
                reach_count[node_id] = reach_count.get(node_id, 0) + 1

        candidates = [node_id for node_id, c in reach_count.items() if c >= 2]
        if not candidates:
            return None

        def sort_key(node_id: str) -> Tuple[int, int, int, str]:
            counts = reach_count.get(node_id, 0)
            dists = [dm.get(node_id, 10**9) for dm in dist_maps]
            return (-counts, max(dists), sum(dists), node_id)

        return sorted(candidates, key=sort_key)[0]

    def _expr_for_required_data_input(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        node = self.model.nodes.get(node_id)
        if node is None:
            raise ReverseGraphCodeError("节点不存在")
        source = self.data_in_edge.get((node_id, port_name))
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            if expr is None:
                raise ReverseGraphCodeError(f"无法解析数据来源变量：{node.title}.{port_name}")
            return expr
        # 常量输入不支持：GraphCodeParser 的 if/match 语义需要变量来源，避免生成无输入的控制节点
        raise ReverseGraphCodeError(f"控制流节点缺少数据来源：{node.title}.{port_name}")

    def _expr_for_optional_data_input(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        node = self.model.nodes.get(node_id)
        if node is None:
            return ""
        source = self.data_in_edge.get((node_id, port_name))
        if source is not None:
            src_node_id, src_port = source
            if (src_node_id, src_port) not in var_mapping:
                self._ensure_data_node_emitted(
                    out_lines=out_lines,
                    node_id=src_node_id,
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )
            expr = var_mapping.get((src_node_id, src_port))
            return expr or ""
        if port_name in (node.input_constants or {}):
            return format_constant((node.input_constants or {}).get(port_name))
        return ""

    def _expr_for_required_match_subject(
        self,
        *,
        node_id: str,
        port_name: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        out_lines: List[str],
        indent: str,
        loop_stack: List[str],
    ) -> str:
        expr = self._expr_for_required_data_input(
            node_id=node_id,
            port_name=port_name,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=loop_stack,
        )
        if not expr.isidentifier() or keyword.iskeyword(expr):
            raise ReverseGraphCodeError(f"match subject 必须是变量名（Name），但当前为：{expr!r}")
        return expr

    def _render_match_case_pattern(self, port_name: str) -> str:
        name = str(port_name or "").strip()
        if name == "默认":
            return "_"
        # 整数 case：允许负数
        if name and (name.isdigit() or (name.startswith("-") and name[1:].isdigit())):
            return name
        return repr(name)

    def _unique_var_name(self, base: str, used: set[str]) -> str:
        candidate = make_valid_identifier(base or "") or "var"
        if keyword.iskeyword(candidate):
            candidate = f"{candidate}_var"
        while candidate in used:
            candidate = f"{candidate}_1"
        used.add(candidate)
        return candidate


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


def _resolve_node_def(*, node: NodeModel, node_library: Dict[str, NodeDef]) -> NodeDef:
    key = f"{node.category}/{node.title}"
    if key in node_library:
        return node_library[key]
    composite_key = f"复合节点/{node.title}"
    if composite_key in node_library:
        return node_library[composite_key]
    raise ReverseGraphCodeError(f"无法在节点库中定位 NodeDef：{key!r}")


def _try_resolve_node_def(*, node: NodeModel, node_library: Dict[str, NodeDef]) -> Optional[NodeDef]:
    """尽量解析 NodeDef；失败时返回 None（避免用 try/except 做控制流）。"""
    key = f"{node.category}/{node.title}"
    if key in node_library:
        return node_library[key]
    composite_key = f"复合节点/{node.title}"
    if composite_key in node_library:
        return node_library[composite_key]
    return None


def _pick_call_name_for_node(
    *,
    node: NodeModel,
    node_def: NodeDef,
    node_library: Dict[str, NodeDef],
    node_name_index: Dict[str, str],
    call_name_candidates_by_identity: Dict[int, List[str]],
) -> str:
    # 优先：title 若可直接作为调用名且能命中 name_index，且映射到同一 NodeDef
    title = str(getattr(node, "title", "") or "").strip()
    if title and title.isidentifier() and (not keyword.iskeyword(title)):
        mapped_key = node_name_index.get(title)
        if mapped_key is not None:
            mapped_def = node_library.get(mapped_key)
            if mapped_def is node_def:
                return title

    identity = id(node_def)
    candidates = call_name_candidates_by_identity.get(identity) or []
    if not candidates:
        raise ReverseGraphCodeError(
            f"节点 {node.category}/{node.title} 缺少可调用名（title 不可用且未找到别名键）"
        )
    return candidates[0]


def _finalize_output_var_names(raw_names: Sequence[str], *, used: set[str]) -> List[str]:
    finalized: List[str] = []
    for raw in raw_names:
        candidate = make_valid_identifier(raw or "")
        if not candidate or candidate == "_":
            candidate = "var"
        while candidate in used or keyword.iskeyword(candidate):
            candidate = f"{candidate}_1"
        used.add(candidate)
        finalized.append(candidate)
    return finalized


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


def _normalize_graph_variables(graph_variables: Sequence[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in graph_variables:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        items.append(entry)
    items.sort(key=lambda d: str(d.get("name", "")))
    return items


def _normalize_graph_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    # 只比较“语义相关”字段，忽略 parsed_at/source_file 等解析时信息
    allow_keys = {
        "graph_type",
        "folder_path",
        "signal_bindings",
        "struct_bindings",
        "custom_variable_file",
    }
    result: Dict[str, Any] = {}
    for key in allow_keys:
        if key in metadata:
            if key == "signal_bindings":
                result[key] = _normalize_signal_bindings(metadata.get(key))
                continue
            if key == "struct_bindings":
                result[key] = _normalize_struct_bindings(metadata.get(key))
                continue
            result[key] = metadata.get(key)
    return result


def _normalize_signal_bindings(value: Any) -> List[Dict[str, Any]]:
    """将 {node_id: {...}} 规范化为与 node_id 无关的稳定列表。"""
    if not isinstance(value, dict):
        return []
    entries: List[Dict[str, Any]] = []
    for info in value.values():
        if not isinstance(info, dict):
            continue
        signal_id = info.get("signal_id")
        entry: Dict[str, Any] = {}
        if isinstance(signal_id, str) and signal_id.strip():
            entry["signal_id"] = signal_id.strip()
        if entry:
            entries.append(entry)
    entries.sort(key=lambda d: (str(d.get("signal_id", "")), json.dumps(d, ensure_ascii=False, sort_keys=True)))
    return entries


def _normalize_struct_bindings(value: Any) -> List[Dict[str, Any]]:
    """将 {node_id: {...}} 规范化为与 node_id 无关的稳定列表。"""
    if not isinstance(value, dict):
        return []
    entries: List[Dict[str, Any]] = []
    for info in value.values():
        if not isinstance(info, dict):
            continue
        entry: Dict[str, Any] = {}
        struct_id = info.get("struct_id")
        struct_name = info.get("struct_name")
        field_names = info.get("field_names")
        if isinstance(struct_id, str) and struct_id.strip():
            entry["struct_id"] = struct_id.strip()
        if isinstance(struct_name, str) and struct_name.strip():
            entry["struct_name"] = struct_name.strip()
        if isinstance(field_names, list):
            entry["field_names"] = [str(x) for x in field_names if str(x).strip() != ""]
        if entry:
            entries.append(entry)
    entries.sort(key=lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True))
    return entries


def _compute_wl_node_hashes(model: GraphModel, *, iterations: int) -> Dict[str, str]:
    raw_nodes = dict(getattr(model, "nodes", {}) or {})
    raw_edges = list((getattr(model, "edges", {}) or {}).values())

    # 语义归一化：对“已连线输入端口”的常量做剔除。
    #
    # 说明：
    # - 解析器在某些场景会同时写入 input_constants 与数据连线（例如：变量既被视为命名常量，
    #   又在 VarEnv 中有连线来源时，两条路径都会生效），但运行期/导出期以连线为准；
    # - 因此“连线覆盖常量”，常量在该端口上等价于冗余信息，不应影响语义签名。
    # 另外：忽略布局层插入的 localvar relay / data copy：
    # - relay/copy 本质是“结构增强/排版辅助”，不应影响 round-trip 语义一致性判断；
    # - 对这些节点的边做“透传/归一化”，再进入 WL hashing。

    # 1) canonical node id（copy -> original；relay 仍保留 id 以便后续透传）
    def _canonical_node_id(node_id: str) -> str:
        node_id_text = str(node_id or "")
        node_obj = raw_nodes.get(node_id_text)
        if node_obj is not None and (_is_data_node_copy(node_obj) or (_COPY_MARKER in node_id_text)):
            original = str(getattr(node_obj, "original_node_id", "") or "") or node_id_text
            return _strip_copy_suffix(original) or node_id_text
        if _COPY_MARKER in node_id_text:
            return _strip_copy_suffix(node_id_text) or node_id_text
        return node_id_text

    # 2) 原始入边索引（供 relay 透传）
    raw_in_by_port: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for e in raw_edges:
        raw_in_by_port[(str(getattr(e, "dst_node", "") or ""), str(getattr(e, "dst_port", "") or ""))] = (
            str(getattr(e, "src_node", "") or ""),
            str(getattr(e, "src_port", "") or ""),
        )

    def _resolve_relay_source(src_node_id: str, src_port: str, *, depth: int = 0) -> Tuple[str, str]:
        if depth > 50:
            return str(src_node_id), str(src_port)
        nid = _canonical_node_id(str(src_node_id))
        port = str(src_port)
        if _is_local_var_relay_node_id(nid) and port == "值":
            upstream = raw_in_by_port.get((nid, "初始值"))
            if upstream is not None:
                return _resolve_relay_source(upstream[0], upstream[1], depth=depth + 1)
        return nid, port

    # 3) 收敛节点集合：剔除 relay/copy 节点（relay 通过透传边表达）
    nodes: Dict[str, NodeModel] = {}
    for node_id, node in raw_nodes.items():
        if node is None:
            continue
        canonical = _canonical_node_id(str(node_id))
        if _is_local_var_relay_node_id(canonical):
            continue
        if canonical not in nodes or _is_data_node_copy(nodes[canonical]) and (not _is_data_node_copy(node)):
            nodes[canonical] = node

    # 4) 重写边：copy 归一 + relay 透传；并丢弃“指向 relay/copy 的边”
    rewritten_edges: List[Tuple[str, str, str, str]] = []
    for e in raw_edges:
        src_node_raw = str(getattr(e, "src_node", "") or "")
        dst_node_raw = str(getattr(e, "dst_node", "") or "")
        src_port = str(getattr(e, "src_port", "") or "")
        dst_port = str(getattr(e, "dst_port", "") or "")
        if not src_node_raw or not dst_node_raw or not src_port or not dst_port:
            continue

        dst_node = _canonical_node_id(dst_node_raw)
        if _is_local_var_relay_node_id(dst_node):
            # relay 节点本身被剔除：其入边不参与语义比较
            continue
        if dst_node not in nodes:
            continue

        src_node, src_port_resolved = _resolve_relay_source(src_node_raw, src_port)
        if _is_local_var_relay_node_id(src_node):
            # relay 的非“值”输出不参与语义比较（理论上不应出现）
            continue
        if src_node not in nodes:
            continue

        rewritten_edges.append((src_node, src_port_resolved, dst_node, dst_port))

    connected_inputs: Dict[str, set[str]] = {nid: set() for nid in nodes.keys()}
    for (src_node_id, src_port, dst_node_id, dst_port) in rewritten_edges:
        connected_inputs.setdefault(dst_node_id, set()).add(str(dst_port))

    base_label: Dict[str, str] = {}
    for node_id, node in nodes.items():
        input_constants = dict(getattr(node, "input_constants", {}) or {})
        connected = connected_inputs.get(node_id)
        if connected:
            for k in list(input_constants.keys()):
                if str(k) in connected:
                    input_constants.pop(k, None)
        label_obj = {
            "category": str(getattr(node, "category", "") or ""),
            "title": str(getattr(node, "title", "") or ""),
            "composite_id": str(getattr(node, "composite_id", "") or ""),
            "inputs": [str(getattr(p, "name", "") or "") for p in (getattr(node, "inputs", []) or [])],
            "outputs": [str(getattr(p, "name", "") or "") for p in (getattr(node, "outputs", []) or [])],
            "input_constants": input_constants,
        }
        base_label[node_id] = _stable_hash_from_obj(label_obj)

    incoming: Dict[str, List[Tuple[str, str, str]]] = {nid: [] for nid in nodes.keys()}
    outgoing: Dict[str, List[Tuple[str, str, str]]] = {nid: [] for nid in nodes.keys()}
    for (src_node_id, src_port, dst_node_id, dst_port) in rewritten_edges:
        if src_node_id not in nodes or dst_node_id not in nodes:
            continue
        outgoing[src_node_id].append((str(src_port), str(dst_port), str(dst_node_id)))
        incoming[dst_node_id].append((str(src_port), str(dst_port), str(src_node_id)))

    current = dict(base_label)
    for _ in range(max(0, int(iterations))):
        next_hash: Dict[str, str] = {}
        for node_id in nodes.keys():
            in_features = [
                f"i:{src_port}->{dst_port}:{current.get(src_node, '<missing>')}"
                for (src_port, dst_port, src_node) in incoming.get(node_id, [])
            ]
            out_features = [
                f"o:{src_port}->{dst_port}:{current.get(dst_node, '<missing>')}"
                for (src_port, dst_port, dst_node) in outgoing.get(node_id, [])
            ]
            in_features.sort()
            out_features.sort()
            combined = {
                "base": base_label.get(node_id, ""),
                "in": in_features,
                "out": out_features,
            }
            next_hash[node_id] = _stable_hash_from_obj(combined)
        current = next_hash
    return current


def _stable_hash_from_obj(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


