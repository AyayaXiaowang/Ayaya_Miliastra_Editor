from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from engine.graph.models.graph_model import GraphModel

from ugc_file_tools.graph.port_types import standardize_graph_model_payload_inplace as _standardize_graph_model_payload_inplace
from ugc_file_tools.node_graph_semantics.graph_generater import is_flow_port_by_node_def as _is_flow_port_by_node_def
from ugc_file_tools.node_graph_semantics.graph_model import (
    normalize_edges_list as _normalize_edges_list,
    normalize_graph_model_payload as _normalize_graph_model_payload,
    normalize_nodes_list as _normalize_nodes_list,
)
from ugc_file_tools.node_graph_semantics.layout import sort_graph_nodes_for_stable_ids as _sort_graph_nodes_for_stable_ids
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    infer_input_type_text_by_dst_node_and_port as _infer_input_type_text_by_dst_node_and_port,
)
from ugc_file_tools.node_graph_semantics.type_inference import (
    infer_output_port_type_by_src_node_and_port as _infer_output_port_type_by_src_node_and_port,
)

from .asset_bundle_builder_blackboard import build_blackboard_entries
from .asset_bundle_builder_connections import build_data_conns_by_dst_pin, build_flow_conns_by_src_pin
from .asset_bundle_builder_constants import _GRAPH_CATEGORY_CONSTS
from .asset_bundle_builder_id_map import _map_composite_id_to_node_type_id_int
from .asset_bundle_builder_node_editor_pack import _load_node_editor_pack_nodes_by_id
from .asset_bundle_builder_node_instances import build_node_instances
from .asset_bundle_builder_proto_helpers import _make_resource_locator
from .asset_bundle_builder_types import GiaAssetBundleGraphExportHints

EdgeTuple = Tuple[str, str, str, str]


@dataclass
class GiaNodeGraphBuildContext:
    gg_root: Path
    graph_scope: str
    resource_class: str
    consts: Mapping[str, Any]
    graph_model: Dict[str, Any]
    graph_variable_type_text_by_name: Dict[str, str]

    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

    node_index_by_graph_node_id: Dict[str, int]
    node_title_by_graph_node_id: Dict[str, str]
    node_payload_by_graph_node_id: Dict[str, Dict[str, Any]]

    node_type_id_int_by_graph_node_id: Dict[str, int]
    node_is_composite_by_graph_node_id: Dict[str, bool]
    node_record_by_graph_node_id: Dict[str, Mapping[str, Any] | None]
    node_def_by_graph_node_id: Dict[str, Any]

    flow_edges: List[EdgeTuple]
    data_edges: List[EdgeTuple]

    send_signal_nodes_with_signal_name_in_edge: set[str]
    listen_signal_nodes_with_signal_name_in_edge: set[str]

    inferred_out_type_text: Dict[Tuple[str, str], str]
    inferred_in_type_text: Dict[Tuple[str, str], str]

    flow_conns_by_src_pin: Dict[Tuple[int, int], List[Dict[str, Any]]]
    data_conns_by_dst_pin: Dict[Tuple[int, int], List[Dict[str, Any]]]

    node_instances: List[Dict[str, Any]]
    blackboard: List[Dict[str, Any]]

    node_graph_msg: Dict[str, Any]
    node_graph_container: Dict[str, Any]


def build_node_graph_build_context(
    *,
    graph_json_object: Dict[str, Any],
    hints: GiaAssetBundleGraphExportHints,
) -> GiaNodeGraphBuildContext:
    """
    GraphModel(JSON) → NodeGraph message 的“上下文构建器”。

    说明：
    - 该函数只负责构造 NodeGraph（含 pins/连线/blackboard），不负责 AssetBundle 外层容器与 dependencies。
    - `.gia` 导出主流程与复合子图导出会共同复用该上下文，避免重复实现与口径漂移。
    """
    gg_root = Path(hints.graph_generater_root).resolve()
    graph_scope = str(hints.graph_scope or "").strip().lower()
    if graph_scope not in {"server", "client"}:
        graph_scope = "server"

    resource_class = str(hints.resource_class or "").strip().upper()
    consts = _GRAPH_CATEGORY_CONSTS.get(resource_class)
    if consts is None:
        raise ValueError(f"不支持的 resource_class（未在内置常量表中找到）：{resource_class!r}")

    graph_model = _normalize_graph_model_payload(graph_json_object)
    if not isinstance(graph_model, dict):
        raise TypeError("graph_model payload must be dict")

    # GraphVariables 必须落在 payload 内：端口有效类型推断依赖 graph_variables。
    if not isinstance(graph_model.get("graph_variables"), list):
        graph_model["graph_variables"] = []

    # graph variables (blackboard): name -> variable_type_text（用于端口类型推断）
    # 说明：`获取节点图变量/设置节点图变量` 的 “变量值” 端口在 GraphModel 中经常保持为“泛型”，
    # 导出时需要用这里的类型信息补齐，否则会被兜底为字符串(6)。
    graph_variable_type_text_by_name: Dict[str, str] = {}
    raw_graph_variables_for_type = graph_model.get("graph_variables")
    if isinstance(raw_graph_variables_for_type, list):
        for var in raw_graph_variables_for_type:
            if not isinstance(var, dict):
                continue
            n = str(var.get("name") or "").strip()
            t = str(var.get("variable_type") or "").strip()
            if not (n and t):
                continue

            # 工程化：GraphVariableConfig(variable_type="字典") 会额外携带 dict_key_type/dict_value_type。
            # 但导出侧的“端口类型证据”需要可被 parse_typed_dict_alias 识别的 typed dict alias 文本，
            # 否则在 `获取/设置节点图变量.变量值(字典)` 场景会因缺少 KV 而 fail-fast。
            if t == "字典":
                k = str(var.get("dict_key_type") or "").strip()
                v = str(var.get("dict_value_type") or "").strip()
                if k and v:
                    # 对齐 Graph_Generater typed dict alias 口径：<键类型>-<值类型>字典
                    t = f"{k}-{v}字典"

            graph_variable_type_text_by_name[n] = t

    nodes = _normalize_nodes_list(graph_model)
    edges = _normalize_edges_list(graph_model)
    sorted_nodes = _sort_graph_nodes_for_stable_ids(nodes)
    if not sorted_nodes:
        raise ValueError("graph_model.nodes 为空：无法导出 .gia")

    # NodeDef 定位唯一真源：GraphModel(JSON) 节点必须携带 node_def_ref（builtin→canonical key；composite→composite_id）
    from ugc_file_tools.node_graph_semantics.graph_generater import ensure_graph_generater_sys_path as _ensure_graph_generater_sys_path

    _ensure_graph_generater_sys_path(gg_root)
    from engine.nodes.node_registry import get_node_registry  # type: ignore[import-not-found]

    registry = get_node_registry(Path(gg_root).resolve(), include_composite=True)
    node_library_by_key: Dict[str, Any] = dict(registry.get_library() or {})
    composite_node_def_by_id: Dict[str, Any] = {}
    for _k, _def in node_library_by_key.items():
        if bool(getattr(_def, "is_composite", False)):
            cid = str(getattr(_def, "composite_id", "") or "").strip()
            if cid and cid not in composite_node_def_by_id:
                composite_node_def_by_id[cid] = _def

    # ===== GraphModel 标准化（导出/写回共用入口）=====
    # 目标：补齐 graph_variables / edge.id / *_port_types / *_declared_types，并复用引擎 EffectivePortTypeResolver
    # 作为“有效端口类型”单一真源。
    node_defs_by_name: Dict[str, Any] = {}
    for node_def in (node_library_by_key or {}).values():
        if node_def is None:
            continue
        if hasattr(node_def, "is_available_in_scope") and callable(getattr(node_def, "is_available_in_scope")):
            if not node_def.is_available_in_scope(str(graph_scope)):
                continue
        name = str(getattr(node_def, "name", "") or "").strip()
        if not name:
            continue
        node_defs_by_name.setdefault(name, node_def)

    _standardize_graph_model_payload_inplace(
        graph_model_payload=graph_model,
        graph_variables=(graph_model.get("graph_variables") if isinstance(graph_model.get("graph_variables"), list) else None),
        workspace_root=Path(gg_root).resolve(),
        scope=str(graph_scope),
        # 导出侧：若上层 pipeline 已经 enrich 过，则跳过重复 enrich；否则会自动 enrich。
        force_reenrich=False,
        fill_missing_edge_ids=True,
        node_defs_by_name=dict(node_defs_by_name),
        node_defs_by_key=dict(node_library_by_key),
        composite_node_def_by_id=dict(composite_node_def_by_id),
    )

    def _resolve_node_def_for_payload(payload: Dict[str, Any]) -> tuple[str, str, Any]:
        node_def_ref = payload.get("node_def_ref")
        if not isinstance(node_def_ref, dict):
            raise ValueError("GraphModel 节点缺少 node_def_ref：导出 .gia 禁止 title fallback")
        kind = str(node_def_ref.get("kind", "") or "").strip()
        key = str(node_def_ref.get("key", "") or "").strip()
        if kind == "builtin":
            node_def = node_library_by_key.get(key)
            if node_def is None:
                raise KeyError(f"node_library 未找到 builtin NodeDef：{key}")
            return kind, key, node_def
        if kind == "event":
            # GraphModel 约定：事件流入口节点的 node_def_ref.kind 为 "event"，其 key 通常为“事件实例标识”（例如信号名），并非 NodeDef canonical key。
            # 导出 `.gia` 仍需要定位真实 NodeDef（用于端口判定与导出 type_id）。
            title = str(payload.get("title") or "").strip()
            category = str(payload.get("category") or "").strip()
            if title == "" or category == "":
                raise ValueError(f"event 节点缺少 title/category，无法推断 NodeDef key：id={payload.get('id')!r}")
            builtin_key = f"{category}/{title}"
            node_def = node_library_by_key.get(builtin_key)
            if node_def is None:
                # 工程化：监听信号事件节点在 GraphModel 中常以 `category=事件节点, title=<信号名>` 表达，
                # 并不会存在 `事件节点/<信号名>` 的 builtin NodeDef。此时应回退到“事件节点/监听信号”语义节点，
                # 让后续端口类型补齐与 signal binding 逻辑继续生效。
                if str(category) == "事件节点":
                    fallback_key = "事件节点/监听信号"
                    fallback_def = node_library_by_key.get(fallback_key)
                    if fallback_def is not None:
                        return "builtin", fallback_key, fallback_def
                raise KeyError(f"node_library 未找到 event NodeDef（builtin_key={builtin_key!r}, event_key={key!r}）")
            return "builtin", builtin_key, node_def
        if kind == "composite":
            node_def = composite_node_def_by_id.get(key)
            if node_def is None:
                raise KeyError(f"node_library 未找到 composite NodeDef（composite_id={key}）")
            return kind, key, node_def
        raise ValueError(f"非法 node_def_ref.kind：{kind!r}")

    node_index_by_graph_node_id: Dict[str, int] = {}
    node_title_by_graph_node_id: Dict[str, str] = {}
    node_payload_by_graph_node_id: Dict[str, Dict[str, Any]] = {}
    for index, (_y, _x, title, node_id, payload) in enumerate(sorted_nodes, start=1):
        if node_id == "":
            raise ValueError("graph node missing id")
        if title == "":
            raise ValueError(f"graph node missing title: id={node_id!r}")
        if not isinstance(payload, dict):
            raise TypeError("graph node payload must be dict")
        node_index_by_graph_node_id[str(node_id)] = int(index)
        node_title_by_graph_node_id[str(node_id)] = str(title)
        node_payload_by_graph_node_id[str(node_id)] = payload

    # === NodeEditorPack 节点画像（用于对齐 ShellIndex/KernelIndex） ===
    nep_nodes_by_id = _load_node_editor_pack_nodes_by_id()
    node_type_id_int_by_graph_node_id: Dict[str, int] = {}
    node_is_composite_by_graph_node_id: Dict[str, bool] = {}
    node_record_by_graph_node_id: Dict[str, Mapping[str, Any] | None] = {}
    node_def_by_graph_node_id: Dict[str, Any] = {}
    for graph_node_id, title in node_title_by_graph_node_id.items():
        payload = node_payload_by_graph_node_id.get(str(graph_node_id))
        if not isinstance(payload, dict):
            continue
        kind, ref_key, node_def = _resolve_node_def_for_payload(payload)
        is_composite = bool(kind == "composite")
        if is_composite:
            node_type_id_int = _map_composite_id_to_node_type_id_int(str(ref_key))
        else:
            node_type_id_int = hints.node_type_id_by_node_def_key.get(str(ref_key))
        if not isinstance(node_type_id_int, int) or int(node_type_id_int) <= 0:
            raise KeyError(f"node_type_semantic_map 未覆盖该节点（无法导出 .gia）：node_def_ref={kind}:{ref_key} title={str(title)!r}")

        node_type_id_int_by_graph_node_id[str(graph_node_id)] = int(node_type_id_int)
        node_is_composite_by_graph_node_id[str(graph_node_id)] = bool(is_composite)
        node_record_by_graph_node_id[str(graph_node_id)] = None if bool(is_composite) else nep_nodes_by_id.get(int(node_type_id_int))
        node_def_by_graph_node_id[str(graph_node_id)] = node_def

    # === 分类 edges（复用 Graph_Generater NodeDef 的“流程端口判定”口径）===
    flow_edges: List[EdgeTuple] = []
    data_edges: List[EdgeTuple] = []
    for edge in list(edges):
        if not isinstance(edge, dict):
            continue
        src_node = str(edge.get("src_node") or "")
        dst_node = str(edge.get("dst_node") or "")
        src_port = str(edge.get("src_port") or "")
        dst_port = str(edge.get("dst_port") or "")
        if src_node == "" or dst_node == "":
            continue
        src_title = node_title_by_graph_node_id.get(src_node, "")
        dst_title = node_title_by_graph_node_id.get(dst_node, "")
        if src_title == "" or dst_title == "":
            raise ValueError(f"edge 引用了未知节点：src={src_node!r} dst={dst_node!r}")
        src_def = node_def_by_graph_node_id.get(str(src_node))
        dst_def = node_def_by_graph_node_id.get(str(dst_node))
        if src_def is None:
            raise KeyError(f"Graph_Generater 节点库未找到节点定义：node_id={src_node!r} title={src_title!r}")
        if dst_def is None:
            raise KeyError(f"Graph_Generater 节点库未找到节点定义：node_id={dst_node!r} title={dst_title!r}")
        src_is_flow = _is_flow_port_by_node_def(node_def=src_def, port_name=str(src_port), is_input=False)
        dst_is_flow = _is_flow_port_by_node_def(node_def=dst_def, port_name=str(dst_port), is_input=True)
        if bool(src_is_flow) != bool(dst_is_flow):
            raise ValueError(
                "edge 端口类型不一致（src/dst 一边是流程一边是数据）："
                f"src={src_title!r}.{src_port!r} dst={dst_title!r}.{dst_port!r}"
            )
        if src_is_flow:
            flow_edges.append((src_node, src_port, dst_node, dst_port))
        else:
            data_edges.append((src_node, src_port, dst_node, dst_port))

    # === Signals: “信号名端口是否存在 data 入边”判定（Send_Signal / Listen_Signal） ===
    send_signal_nodes_with_signal_name_in_edge: set[str] = set()
    listen_signal_nodes_with_signal_name_in_edge: set[str] = set()
    for _src_node_id, _src_port, _dst_node_id, _dst_port in list(data_edges):
        dst_type_id_int = node_type_id_int_by_graph_node_id.get(str(_dst_node_id))
        if not (isinstance(dst_type_id_int, int) and str(_dst_port).strip() == "信号名"):
            continue
        if int(dst_type_id_int) == 300000:
            send_signal_nodes_with_signal_name_in_edge.add(str(_dst_node_id))
        elif int(dst_type_id_int) == 300001:
            listen_signal_nodes_with_signal_name_in_edge.add(str(_dst_node_id))

    # === 类型推断（用于泛型端口）===
    inferred_out_type_text = _infer_output_port_type_by_src_node_and_port(edges=edges, graph_node_by_graph_node_id=node_payload_by_graph_node_id)
    inferred_in_type_text = _infer_input_type_text_by_dst_node_and_port(
        edges=edges,
        graph_node_by_graph_node_id=node_payload_by_graph_node_id,
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
    )

    # === 连接聚合 ===
    flow_conns_by_src_pin = build_flow_conns_by_src_pin(
        flow_edges=list(flow_edges),
        node_index_by_graph_node_id=node_index_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        node_def_by_graph_node_id=node_def_by_graph_node_id,
        node_payload_by_graph_node_id=node_payload_by_graph_node_id,
        node_type_id_int_by_graph_node_id=node_type_id_int_by_graph_node_id,
        node_record_by_graph_node_id=node_record_by_graph_node_id,
    )
    data_conns_by_dst_pin = build_data_conns_by_dst_pin(
        data_edges=list(data_edges),
        node_index_by_graph_node_id=node_index_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        node_def_by_graph_node_id=node_def_by_graph_node_id,
        node_payload_by_graph_node_id=node_payload_by_graph_node_id,
        node_type_id_int_by_graph_node_id=node_type_id_int_by_graph_node_id,
        node_record_by_graph_node_id=node_record_by_graph_node_id,
        send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge or set()),
        listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge or set()),
    )

    # === build nodes ===
    node_instances = build_node_instances(
        graph_json_object=graph_json_object,
        graph_scope=str(graph_scope),
        consts=consts,
        hints=hints,
        node_index_by_graph_node_id=node_index_by_graph_node_id,
        node_payload_by_graph_node_id=node_payload_by_graph_node_id,
        node_type_id_int_by_graph_node_id=node_type_id_int_by_graph_node_id,
        node_is_composite_by_graph_node_id=node_is_composite_by_graph_node_id,
        node_record_by_graph_node_id=node_record_by_graph_node_id,
        node_def_by_graph_node_id=node_def_by_graph_node_id,
        flow_conns_by_src_pin=dict(flow_conns_by_src_pin),
        data_conns_by_dst_pin=dict(data_conns_by_dst_pin),
        inferred_out_type_text=dict(inferred_out_type_text),
        inferred_in_type_text=dict(inferred_in_type_text),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge or set()),
        listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge or set()),
    )

    blackboard = build_blackboard_entries(graph_model=graph_model)

    graph_locator = _make_resource_locator(
        origin=int(consts["GraphOrigin"]),
        category=int(consts["GraphCategory"]),
        kind=int(consts["GraphKind"]),
        guid=0,
        runtime_id=int(hints.graph_id_int),
    )
    node_graph_msg: Dict[str, Any] = {
        "1": graph_locator,
        "2": str(hints.graph_name),
        "3": node_instances,
        "6": blackboard,
    }
    if resource_class in {"BOOLEAN_FILTER_GRAPH", "INTEGER_FILTER_GRAPH", "SKILL_NODE_GRAPH"}:
        node_graph_msg["100"] = 1
        node_graph_msg["101"] = 0.3

    node_graph_container: Dict[str, Any] = {"1": {"1": node_graph_msg}}

    return GiaNodeGraphBuildContext(
        gg_root=Path(gg_root),
        graph_scope=str(graph_scope),
        resource_class=str(resource_class),
        consts=consts,
        graph_model=dict(graph_model),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        nodes=list(nodes),
        edges=list(edges),
        node_index_by_graph_node_id=dict(node_index_by_graph_node_id),
        node_title_by_graph_node_id=dict(node_title_by_graph_node_id),
        node_payload_by_graph_node_id=dict(node_payload_by_graph_node_id),
        node_type_id_int_by_graph_node_id=dict(node_type_id_int_by_graph_node_id),
        node_is_composite_by_graph_node_id=dict(node_is_composite_by_graph_node_id),
        node_record_by_graph_node_id=dict(node_record_by_graph_node_id),
        node_def_by_graph_node_id=dict(node_def_by_graph_node_id),
        flow_edges=list(flow_edges),
        data_edges=list(data_edges),
        send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge),
        listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge),
        inferred_out_type_text=dict(inferred_out_type_text),
        inferred_in_type_text=dict(inferred_in_type_text),
        flow_conns_by_src_pin=dict(flow_conns_by_src_pin),
        data_conns_by_dst_pin=dict(data_conns_by_dst_pin),
        node_instances=list(node_instances),
        blackboard=list(blackboard),
        node_graph_msg=node_graph_msg,
        node_graph_container=node_graph_container,
    )

