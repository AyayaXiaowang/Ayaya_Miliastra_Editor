from __future__ import annotations

"""
GraphModel 端口类型补齐（写回/导出共用）。

动机：
- 多个链路需要在 GraphModel.serialize() 的 payload 上补齐端口类型（含泛型端口的具体类型推断）；
- 该能力属于可复用库逻辑，不能放在 `ugc_file_tools.commands/`（入口层）中被其他模块反向依赖。
"""

from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, List


def load_node_defs_by_name_from_registry(*, workspace_root: Path, scope: str) -> Dict[str, Any]:
    """从 NodeRegistry 加载节点库，构建 {节点名: NodeDef} 映射。"""
    scope_text = str(scope or "").strip() or "server"
    node_defs_by_name: Dict[str, Any] = {}

    get_node_registry = getattr(import_module("engine.nodes.node_registry"), "get_node_registry")
    registry = get_node_registry(Path(workspace_root).resolve(), include_composite=True)
    library = registry.get_library()
    for node_def in (library or {}).values():
        if node_def is None:
            continue
        if hasattr(node_def, "is_available_in_scope") and callable(getattr(node_def, "is_available_in_scope")):
            if not node_def.is_available_in_scope(scope_text):
                continue
        name = str(getattr(node_def, "name", "") or "").strip()
        if not name:
            continue
        node_defs_by_name.setdefault(name, node_def)
    return node_defs_by_name


def load_node_library_maps_from_registry(
    *,
    workspace_root: Path,
    scope: str,
    include_composite: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    从 NodeRegistry 加载节点库，并构建：
    - node_defs_by_name: {NodeDef.name -> NodeDef}
    - node_defs_by_key:  {canonical_key -> NodeDef}（registry.get_library() 的 key）
    - composite_node_def_by_id: {composite_id -> NodeDef}

    说明：
    - 会按 scope 过滤不可用节点；
    - 该函数用于“GraphModel 标准化入口”，供导出/写回共用，避免各处重复扫描 registry。
    """
    scope_text = str(scope or "").strip() or "server"
    get_node_registry = getattr(import_module("engine.nodes.node_registry"), "get_node_registry")
    registry = get_node_registry(Path(workspace_root).resolve(), include_composite=bool(include_composite))
    library = dict(registry.get_library() or {})

    node_defs_by_key: Dict[str, Any] = {}
    node_defs_by_name: Dict[str, Any] = {}
    composite_node_def_by_id: Dict[str, Any] = {}

    for k, node_def in list(library.items()):
        if node_def is None:
            continue
        if hasattr(node_def, "is_available_in_scope") and callable(getattr(node_def, "is_available_in_scope")):
            if not node_def.is_available_in_scope(scope_text):
                continue
        key = str(k or "").strip()
        if key:
            node_defs_by_key.setdefault(key, node_def)
        name = str(getattr(node_def, "name", "") or "").strip()
        if name:
            node_defs_by_name.setdefault(name, node_def)
        if bool(getattr(node_def, "is_composite", False)):
            cid = str(getattr(node_def, "composite_id", "") or "").strip()
            if cid:
                composite_node_def_by_id.setdefault(cid, node_def)

    return node_defs_by_name, node_defs_by_key, composite_node_def_by_id


def _resolve_node_def_for_model(
    node_model: Any,
    *,
    node_defs_by_name: Mapping[str, Any],
    node_defs_by_key: Mapping[str, Any] | None,
    composite_node_def_by_id: Mapping[str, Any] | None,
    allow_title_fallback: bool,
) -> Any:
    """
    解析 NodeModel → NodeDef。

    优先级：
    - node_def_ref（builtin/composite/event）
    - （可选）回退到 title → NodeDef.name（仅用于离线迁移/兼容诊断；运行态禁用）

    注意：导出/写回链路的 NodeDef 定位唯一真源应为 node_def_ref；title 回退仅用于兼容。
    """
    node_def_ref = getattr(node_model, "node_def_ref", None)
    if node_def_ref is not None:
        kind = str(getattr(node_def_ref, "kind", "") or "").strip()
        key = str(getattr(node_def_ref, "key", "") or "").strip()
        if kind == "builtin" and key and isinstance(node_defs_by_key, dict):
            hit = node_defs_by_key.get(key)
            if hit is not None:
                return hit
        if kind == "composite" and key and isinstance(composite_node_def_by_id, dict):
            hit = composite_node_def_by_id.get(key)
            if hit is not None:
                return hit
        if kind == "event":
            # event 的 key 通常为事件实例标识；需按 (category/title) 映射回 builtin key
            title = str(getattr(node_model, "title", "") or "").strip()
            category = str(getattr(node_model, "category", "") or "").strip()
            builtin_key = f"{category}/{title}" if title and category else ""
            if builtin_key and isinstance(node_defs_by_key, dict):
                hit = node_defs_by_key.get(builtin_key)
                if hit is not None:
                    return hit
            # 工程化：监听信号事件节点在 GraphModel 中常以 `category=事件节点, title=<信号名>` 表达，
            # 并不会存在 `事件节点/<信号名>` 的 builtin NodeDef。此时应回退到“监听信号”语义节点，
            # 让 EffectivePortTypeResolver 基于 signal binding 补齐动态参数端口类型。
            if category == "事件节点" and isinstance(node_defs_by_key, dict):
                hit = node_defs_by_key.get("事件节点/监听信号")
                if hit is not None:
                    return hit

    if bool(allow_title_fallback):
        title = str(getattr(node_model, "title", "") or "").strip()
        if title:
            return dict(node_defs_by_name or {}).get(title)
    return None


def enrich_graph_model_with_port_types(
    *,
    graph_model: Any,
    graph_model_payload: Dict[str, Any],
    node_defs_by_name: Dict[str, Any],
    node_defs_by_key: Optional[Dict[str, Any]] = None,
    composite_node_def_by_id: Optional[Dict[str, Any]] = None,
    allow_title_fallback: bool = False,
) -> None:
    """在 graph_model.serialize() 的 payload 内，为每个节点补充 input/output 端口类型信息。

    写入字段（写入到每个 node dict）：
    - input_port_types: {port_name: concrete_type}
    - output_port_types: {port_name: concrete_type}
    - input_port_declared_types: {port_name: declared_type}
    - output_port_declared_types: {port_name: declared_type}
    """
    nodes_list = graph_model_payload.get("nodes")
    if not isinstance(nodes_list, list) or not nodes_list:
        return

    # 端口类型补齐必须与 UI/graph_cache 共享同一套“有效类型”口径：直接复用引擎侧 EffectivePortTypeResolver。
    port_type_effective = import_module("engine.graph.port_type_effective_resolver")
    EffectivePortTypeResolver = getattr(port_type_effective, "EffectivePortTypeResolver")
    safe_get_port_type_from_node_def = getattr(port_type_effective, "safe_get_port_type_from_node_def")

    node_model_by_id = getattr(graph_model, "nodes", {}) or {}
    if not isinstance(node_model_by_id, dict):
        return

    node_defs_by_key_map: Dict[str, Any] | None = dict(node_defs_by_key or {}) if isinstance(node_defs_by_key, dict) else None
    composite_node_def_by_id_map: Dict[str, Any] | None = (
        dict(composite_node_def_by_id or {}) if isinstance(composite_node_def_by_id, dict) else None
    )

    def _node_def_resolver(node_model: Any) -> Any:
        return _resolve_node_def_for_model(
            node_model,
            node_defs_by_name=dict(node_defs_by_name or {}),
            node_defs_by_key=node_defs_by_key_map,
            composite_node_def_by_id=composite_node_def_by_id_map,
            allow_title_fallback=bool(allow_title_fallback),
        )

    resolver = EffectivePortTypeResolver(graph_model, node_def_resolver=_node_def_resolver)

    for node_payload in nodes_list:
        if not isinstance(node_payload, dict):
            continue
        node_id = str(node_payload.get("id") or "")
        node_model = node_model_by_id.get(node_id)
        if node_model is None:
            continue
        node_def = _node_def_resolver(node_model)
        if node_def is None:
            if not bool(allow_title_fallback):
                node_def_ref = getattr(node_model, "node_def_ref", None)
                kind = str(getattr(node_def_ref, "kind", "") or "").strip() if node_def_ref is not None else ""
                key = str(getattr(node_def_ref, "key", "") or "").strip() if node_def_ref is not None else ""
                category = str(getattr(node_model, "category", "") or "").strip()
                title = str(getattr(node_model, "title", "") or "").strip()
                raise KeyError(
                    "NodeDef 定位失败（运行态禁止 title fallback）："
                    f"node_id={node_id!r}, kind={kind!r}, key={key!r}, category={category!r}, title={title!r}"
                )
            continue

        input_declared: Dict[str, str] = {}
        output_declared: Dict[str, str] = {}
        input_types: Dict[str, str] = {}
        output_types: Dict[str, str] = {}

        # inputs
        for port_obj in getattr(node_model, "inputs", []) or []:
            port_name = str(getattr(port_obj, "name", "") or "")
            if not port_name:
                continue
            declared = str(safe_get_port_type_from_node_def(node_def, port_name, is_input=True) or "")
            input_declared[port_name] = declared
            resolved = str(resolver.resolve(str(node_id), str(port_name), is_input=True) or "").strip()
            input_types[port_name] = resolved or "泛型"

        # outputs
        for port_obj in getattr(node_model, "outputs", []) or []:
            port_name = str(getattr(port_obj, "name", "") or "")
            if not port_name:
                continue
            declared = str(safe_get_port_type_from_node_def(node_def, port_name, is_input=False) or "")
            output_declared[port_name] = declared
            resolved = str(resolver.resolve(str(node_id), str(port_name), is_input=False) or "").strip()
            output_types[port_name] = resolved or "泛型"

        node_payload["input_port_declared_types"] = input_declared
        node_payload["output_port_declared_types"] = output_declared
        node_payload["input_port_types"] = input_types
        node_payload["output_port_types"] = output_types


def standardize_graph_model_payload_inplace(
    *,
    graph_model_payload: Dict[str, Any],
    graph_variables: List[Dict[str, Any]] | None,
    workspace_root: Path,
    scope: str,
    force_reenrich: bool,
    fill_missing_edge_ids: bool = True,
    allow_title_fallback: bool = False,
    node_defs_by_name: Optional[Dict[str, Any]] = None,
    node_defs_by_key: Optional[Dict[str, Any]] = None,
    composite_node_def_by_id: Optional[Dict[str, Any]] = None,
) -> None:
    """
    GraphModel(JSON) 标准化入口（导出/写回共用）：

    - 补齐 `graph_variables` 到 payload（有些输入会把 graph_variables 放在外层）；
    - 补齐 edge.id（GraphModel.deserialize 严格要求，缺失会导致 enrich 失败）；
    - 统一补齐每个节点的：
      - `input_port_types/output_port_types`（有效类型快照）
      - `input_port_declared_types/output_port_declared_types`（声明类型快照）

    说明：
    - 默认会 fail-fast 抛错：输入结构不符合 GraphModel.deserialize 要求时直接报错；
    - `force_reenrich=True` 用于写回侧：即使已有快照也重新 enrich，避免历史错误快照短路；
    - 导出侧可用 `force_reenrich=False`：当快照已齐全时跳过重复 enrich。
    - `allow_title_fallback=True` 仅用于离线迁移/兼容诊断：允许在缺失/无法解析 `node_def_ref` 时回退 title → NodeDef.name；
      运行态/交付边界（导出/写回）默认禁用该回退，避免将“猜中错误 NodeDef”的漂移固化进产物。
    """
    if not isinstance(graph_model_payload, dict):
        raise TypeError("graph_model_payload must be dict")

    # 1) GraphVariables 注入（端口类型推断依赖）
    if not isinstance(graph_model_payload.get("graph_variables"), list):
        if graph_variables is not None and isinstance(graph_variables, list) and graph_variables:
            graph_model_payload["graph_variables"] = list(graph_variables)
        else:
            graph_model_payload["graph_variables"] = []

    # 2) edge.id 补齐（仅用于反序列化与推断，不改变导出/写回语义）
    if bool(fill_missing_edge_ids):
        edges_obj = graph_model_payload.get("edges")
        if isinstance(edges_obj, list) and edges_obj:
            for idx, e in enumerate(list(edges_obj), start=1):
                if not isinstance(e, dict):
                    continue
                edge_id = str(e.get("id") or "").strip()
                if edge_id == "":
                    e["id"] = f"edge_{int(idx)}"
        elif isinstance(edges_obj, dict) and edges_obj:
            # dict[id->edge] 形态：仅对缺 id 的 value 补齐（id 键不一定等于 edge.id）
            for idx, e in enumerate(list(edges_obj.values()), start=1):
                if not isinstance(e, dict):
                    continue
                edge_id = str(e.get("id") or "").strip()
                if edge_id == "":
                    e["id"] = f"edge_{int(idx)}"

    # 3) 是否需要 enrich
    need_enrich = bool(force_reenrich)
    if not need_enrich:
        nodes = graph_model_payload.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            need_enrich = True
        else:
            for n in list(nodes):
                if not isinstance(n, dict):
                    continue
                ipt = n.get("input_port_types")
                opt = n.get("output_port_types")
                ipd = n.get("input_port_declared_types")
                opd = n.get("output_port_declared_types")
                if not (isinstance(ipt, dict) and isinstance(opt, dict) and isinstance(ipd, dict) and isinstance(opd, dict)):
                    need_enrich = True
                    break

    if not need_enrich:
        return

    # 4) enrich：复用引擎 EffectivePortTypeResolver（与 UI/预览同口径）
    GraphModel = getattr(import_module("engine.graph.models.graph_model"), "GraphModel")
    graph_model_obj = GraphModel.deserialize(dict(graph_model_payload))

    # 允许上层传入预加载映射，避免重复扫描 registry
    if node_defs_by_name is None or node_defs_by_key is None or composite_node_def_by_id is None:
        nd_name, nd_key, nd_comp = load_node_library_maps_from_registry(
            workspace_root=Path(workspace_root).resolve(),
            scope=str(scope),
            include_composite=True,
        )
        node_defs_by_name = nd_name
        node_defs_by_key = nd_key
        composite_node_def_by_id = nd_comp

    enrich_graph_model_with_port_types(
        graph_model=graph_model_obj,
        graph_model_payload=graph_model_payload,
        node_defs_by_name=dict(node_defs_by_name or {}),
        node_defs_by_key=dict(node_defs_by_key or {}) if isinstance(node_defs_by_key, dict) else None,
        composite_node_def_by_id=dict(composite_node_def_by_id or {}) if isinstance(composite_node_def_by_id, dict) else None,
        allow_title_fallback=bool(allow_title_fallback),
    )


__all__ = [
    "enrich_graph_model_with_port_types",
    "load_node_defs_by_name_from_registry",
    "load_node_library_maps_from_registry",
    "standardize_graph_model_payload_inplace",
]
