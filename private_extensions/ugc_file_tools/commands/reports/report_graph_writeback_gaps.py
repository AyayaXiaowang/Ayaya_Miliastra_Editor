from __future__ import annotations

"""
report_graph_writeback_gaps.py

用途：
- 对比 “GraphModel(JSON) 需要写回的内容” vs “当前模板样本库（template_gil + 可选 template_library_dir）”
  输出一份可重复的 gap 报告，帮助你在补充真源样本后立即看到覆盖提升。

报告范围（目前聚焦 server 写回链路最关键的 3 类缺口）：
- 缺 node type_id 模板：GraphModel 里出现了某节点，但模板库无对应 type_id 的 node 样本可克隆。
- 缺 record 形态/覆盖：
  - data-link record：dst_type_id + slot_index 的模板 record 是否存在（模板缺失时会退化为 schema 兜底写入）。
  - OutParam record：type_id + out_index + var_type 的模板 record 是否存在（缺失时当前实现不会凭空新增）。
- 缺默认值写回规则：
  - 当前 input_constants 写回不支持 “字典”(VarType=27) 常量；若 GraphModel 常量端口类型为字典，会在写回阶段报错。
  - 列表常量若以字符串形式提供（例如 "[1,2,3]"），仅部分列表类型支持解析；其余类型要求上游提供真正的 list/tuple。

约束：
- 不使用 try/except；失败直接抛错（fail-closed）。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.model_files import iter_graph_model_json_files_from_paths
from ugc_file_tools.graph.model_ir import normalize_edges_list, normalize_nodes_list, pick_graph_model_payload_and_metadata
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root
from ugc_file_tools.scope_utils import normalize_scope_or_default, normalize_scope_or_raise
from ugc_file_tools.var_type_map import try_map_server_port_type_text_to_var_type_id


def _normalize_scope_text(text: str) -> str:
    # 兼容：保留旧函数名，底层实现收敛到 scope_utils 单一真源。
    return normalize_scope_or_raise(text)


def _load_semantic_map(mapping_path: Path) -> Tuple[Dict[str, Dict[str, List[int]]], Dict[int, Dict[str, str]]]:
    """读取 node_type_semantic_map.json。

    返回：
    - name_to_ids_by_scope: scope -> node_name -> [type_id_int, ...]
    - type_id_to_meta: type_id_int -> {"scope": "server/client", "node_name": "<cn_name>"}
    """
    doc = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise TypeError("node_type_semantic_map.json must be dict")

    name_to_ids_by_scope: Dict[str, Dict[str, List[int]]] = {"server": {}, "client": {}}
    type_id_to_meta: Dict[int, Dict[str, str]] = {}

    for type_id_str, entry in doc.items():
        if not isinstance(entry, dict):
            continue
        if not str(type_id_str).isdigit():
            continue
        scope = str(entry.get("scope") or "").strip().lower()
        if scope not in ("server", "client"):
            continue
        name = str(entry.get("graph_generater_node_name") or "").strip()
        if name == "":
            continue
        type_id_int = int(type_id_str)
        name_to_ids_by_scope.setdefault(scope, {}).setdefault(name, []).append(type_id_int)
        type_id_to_meta[type_id_int] = {"scope": str(scope), "node_name": str(name)}

    for scope, mp in name_to_ids_by_scope.items():
        for name, ids in mp.items():
            mp[name] = sorted(set(int(v) for v in ids))

    return name_to_ids_by_scope, type_id_to_meta


def _build_node_defs_by_scope(*, graph_generater_root: Path) -> Dict[str, Dict[str, Any]]:
    """加载 Graph_Generater 节点库，并按 scope 分组返回：scope -> {节点名: NodeDef}。"""
    from ugc_file_tools.node_graph_semantics.graph_generater import ensure_graph_generater_sys_path as _ensure_graph_generater_sys_path

    root = Path(graph_generater_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))

    _ensure_graph_generater_sys_path(root)

    from engine.nodes.node_registry import get_node_registry  # type: ignore[import-not-found]

    registry = get_node_registry(root, include_composite=False)
    library = registry.get_library()

    node_defs_by_scope: Dict[str, Dict[str, Any]] = {"server": {}, "client": {}}
    for node_def in library.values():
        if node_def is None:
            continue
        name = str(getattr(node_def, "name", "") or "").strip()
        if name == "":
            continue
        if node_def.is_available_in_scope("server"):
            node_defs_by_scope.setdefault("server", {}).setdefault(name, node_def)
        if node_def.is_available_in_scope("client"):
            node_defs_by_scope.setdefault("client", {}).setdefault(name, node_def)
    return node_defs_by_scope


def _is_flow_port_name_text(port_name: str) -> bool:
    # 与 GraphModel 的中文端口名约定对齐：流程口一般包含“流程”二字。
    # （更严格的判断在 Graph_Generater 内部，但这里作为可移植的 report 工具先采用保守实现。）
    return "流程" in str(port_name or "")


def _try_map_port_type_text_to_var_type_int(port_type_text: str) -> Optional[int]:
    """对齐 node_graph_semantics.var_base.map_server_port_type_to_var_type_id 的映射口径（但不抛异常）。"""
    return try_map_server_port_type_text_to_var_type_id(port_type_text)


def _filter_data_ports_by_node_def(
    *,
    ports: Sequence[Any],
    node_def: Optional[Any],
    is_input: bool,
) -> List[str]:
    """按 NodeDef 的端口类型过滤掉 flow ports，返回 data ports（字符串列表）。

    对齐 node_graph_writeback.edges_writeback 的口径：flow/data 端口区分由 NodeDef.get_port_type 决定。
    """
    from ugc_file_tools.node_graph_semantics.graph_generater import is_flow_port_by_node_def as _is_flow_port_by_node_def

    if node_def is None:
        return [str(p) for p in ports if not _is_flow_port_name_text(str(p))]
    return [
        str(p)
        for p in ports
        if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=bool(is_input))
    ]


def _is_list_constant_string_supported(port_type_text: str, raw_value: str) -> bool:
    """
    对齐 var_base._coerce_constant_value_for_port_type 的能力边界：
    - 允许 "[]" / "()" 作为空列表
    - 非空列表的字符串解析仅覆盖：整数类列表 / 浮点数列表 / 布尔值列表 / 字符串列表
    """
    t = str(port_type_text or "").strip()
    s = str(raw_value or "").strip()
    if s in ("[]", "()"):
        return True
    if not ((s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")"))):
        return False
    supported_non_empty = {
        "整数列表",
        "GUID列表",
        "配置ID列表",
        "元件ID列表",
        "阵营列表",
        "浮点数列表",
        "布尔值列表",
        "字符串列表",
    }
    return t in supported_non_empty


@dataclass(frozen=True, slots=True)
class _OutParamNeed:
    node_title: str
    type_id_int: int
    out_index: int
    out_port: str
    desired_type_text: str
    desired_var_type_int: int


def build_report(
    *,
    template_gil_path: Path,
    template_graph_id_int: int,
    template_library_dir: Optional[Path],
    mapping_path: Path,
    graph_generater_root: Path,
    default_scope: str,
    graph_model_paths: Sequence[str],
) -> Dict[str, Any]:
    default_scope_norm = normalize_scope_or_default(default_scope, default_scope="server")
    name_to_ids_by_scope, type_id_to_meta = _load_semantic_map(Path(mapping_path))

    # NodeDef：用于严格对齐写回管线的 flow/data 端口判定，以及动态端口 slot_index→pin_index 映射
    node_defs_by_scope = _build_node_defs_by_scope(graph_generater_root=Path(graph_generater_root))
    from ugc_file_tools.node_graph_semantics.pin_rules import map_inparam_pin_index_for_node

    graph_json_files = iter_graph_model_json_files_from_paths(list(graph_model_paths))

    # ===== 收集 GraphModel 侧“需求” =====
    missing_mapping_titles_all: Set[str] = set()
    ambiguous_titles_all: Dict[str, Set[int]] = {}
    required_type_ids_all: Set[int] = set()

    # data-link record 的模板 key 口径：record pin_index（写回时的 InParam.index），不是 GraphModel 的 slot_index。
    required_data_pins_by_type_id: Dict[int, Set[int]] = {}
    required_data_pin_examples: Dict[Tuple[int, int], Dict[str, Any]] = {}
    required_outparam_templates: List[_OutParamNeed] = []

    # default value writeback gaps（从 GraphModel 的 input_constants 推断）
    input_constant_dict_ports: List[Dict[str, Any]] = []
    input_constant_unknown_port_types: List[Dict[str, Any]] = []
    input_constant_list_string_unsupported: List[Dict[str, Any]] = []

    per_graph: List[Dict[str, Any]] = []

    for json_path in graph_json_files:
        obj = json.loads(Path(json_path).read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise TypeError(f"GraphModel JSON 顶层必须是 dict：{str(json_path)!r}")

        metadata, graph_model = pick_graph_model_payload_and_metadata(obj)
        if not isinstance(graph_model, dict):
            raise TypeError(f"graph_model 不是 dict：{str(json_path)!r}")

        graph_name = str(metadata.get("graph_name") or graph_model.get("graph_name") or json_path.stem).strip()

        scope = str(metadata.get("graph_type") or metadata.get("graph_scope") or "").strip().lower()
        if scope not in ("server", "client"):
            scope = default_scope_norm

        nodes = normalize_nodes_list(graph_model)
        edges = normalize_edges_list(graph_model)

        node_by_id: Dict[str, Dict[str, Any]] = {}
        title_by_node_id: Dict[str, str] = {}
        for n in nodes:
            node_id = str(n.get("id") or "").strip()
            title = str(n.get("title") or "").strip()
            if node_id:
                node_by_id[node_id] = n
            if node_id and title:
                title_by_node_id[node_id] = title

        titles = [str(n.get("title") or "").strip() for n in nodes]
        titles = [t for t in titles if t]
        unique_titles = sorted(set(titles))

        name_to_ids = name_to_ids_by_scope.get(scope, {})
        title_to_type_id: Dict[str, int] = {}

        missing_mapping: List[str] = []
        ambiguous: List[Dict[str, Any]] = []
        for title in unique_titles:
            ids = name_to_ids.get(title)
            if not ids:
                missing_mapping.append(title)
                missing_mapping_titles_all.add(title)
                continue
            if len(ids) != 1:
                ids_set = set(int(v) for v in ids)
                ambiguous.append({"title": title, "type_ids": sorted(list(ids_set))})
                ambiguous_titles_all.setdefault(title, set()).update(ids_set)
                continue
            title_to_type_id[title] = int(ids[0])
            required_type_ids_all.add(int(ids[0]))

        # ---- data edges -> dst slot_index needs ----
        edge_slot_miss: List[Dict[str, Any]] = []
        for e in edges:
            src_node = str(e.get("src_node") or "").strip()
            dst_node = str(e.get("dst_node") or "").strip()
            src_port = str(e.get("src_port") or "").strip()
            dst_port = str(e.get("dst_port") or "").strip()
            if not src_node or not dst_node or not src_port or not dst_port:
                continue

            src_title = title_by_node_id.get(src_node, "")
            dst_title = title_by_node_id.get(dst_node, "")
            node_defs = node_defs_by_scope.get(scope, {})
            src_def = node_defs.get(str(src_title))
            dst_def = node_defs.get(str(dst_title))

            # 严格按 NodeDef 判断 flow/data（与写回管线一致）；缺 NodeDef 时退化为端口名包含“流程”的判断
            from ugc_file_tools.node_graph_semantics.graph_generater import is_flow_port_by_node_def as _is_flow_port_by_node_def

            src_is_flow = (
                _is_flow_port_by_node_def(node_def=src_def, port_name=str(src_port), is_input=False)
                if src_def is not None
                else _is_flow_port_name_text(str(src_port))
            )
            dst_is_flow = (
                _is_flow_port_by_node_def(node_def=dst_def, port_name=str(dst_port), is_input=True)
                if dst_def is not None
                else _is_flow_port_name_text(str(dst_port))
            )
            if bool(src_is_flow) or bool(dst_is_flow):
                continue

            dst_payload = node_by_id.get(dst_node)
            if not isinstance(dst_payload, dict):
                continue
            dst_type_id = title_to_type_id.get(dst_title)
            if not isinstance(dst_type_id, int):
                continue
            inputs_value = dst_payload.get("inputs")
            inputs_all = [str(x) for x in inputs_value] if isinstance(inputs_value, list) else []
            data_inputs = _filter_data_ports_by_node_def(ports=inputs_all, node_def=dst_def, is_input=True)
            if dst_port not in data_inputs:
                edge_slot_miss.append(
                    {
                        "dst_node": dst_node,
                        "dst_title": dst_title,
                        "dst_port": dst_port,
                        "data_inputs": data_inputs,
                    }
                )
                continue

            data_input_slot_index = int(data_inputs.index(dst_port))
            record_pin_index = int(
                map_inparam_pin_index_for_node(
                    node_title=str(dst_title), port_name=str(dst_port), slot_index=int(data_input_slot_index)
                )
            )
            required_data_pins_by_type_id.setdefault(int(dst_type_id), set()).add(int(record_pin_index))

            # 将“端口类型/VarType”写入示例：后续 auto-wire 可直接使用报告里的 VarType，
            # 从而不需要再反向打开 GraphModel JSON（避免把 out/ 产物变成输入依赖）。
            dst_port_type_text = ""
            input_port_types = dst_payload.get("input_port_types")
            if not isinstance(input_port_types, dict):
                input_port_types = dst_payload.get("effective_input_types")
            if isinstance(input_port_types, dict):
                t0 = input_port_types.get(dst_port)
                if isinstance(t0, str) and t0.strip():
                    dst_port_type_text = t0.strip()
            dst_var_type_int = (
                _try_map_port_type_text_to_var_type_int(dst_port_type_text) if dst_port_type_text else None
            )

            key = (int(dst_type_id), int(record_pin_index))
            required_data_pin_examples.setdefault(
                key,
                {
                    "graph_json": str(json_path),
                    "graph_name": graph_name,
                    "scope": str(scope),
                    "dst_title": str(dst_title),
                    "dst_port": str(dst_port),
                    "dst_port_type_text": str(dst_port_type_text),
                    "dst_var_type_int": (int(dst_var_type_int) if isinstance(dst_var_type_int, int) else None),
                    "data_input_slot_index": int(data_input_slot_index),
                    "record_pin_index": int(record_pin_index),
                },
            )

        # ---- output_port_types -> OutParam template needs ----
        outparam_needs_local: List[Dict[str, Any]] = []
        for node_id, payload in node_by_id.items():
            title = str(payload.get("title") or "").strip()
            type_id = title_to_type_id.get(title)
            if not isinstance(type_id, int):
                continue
            outputs_value = payload.get("outputs")
            outputs_all = [str(x) for x in outputs_value] if isinstance(outputs_value, list) else []
            node_def = node_defs_by_scope.get(scope, {}).get(str(title))
            data_outputs = _filter_data_ports_by_node_def(ports=outputs_all, node_def=node_def, is_input=False)
            out_types = payload.get("output_port_types")
            if not isinstance(out_types, dict):
                out_types = payload.get("effective_output_types")
            if not isinstance(out_types, dict):
                continue
            for out_index, out_port_name in enumerate(data_outputs):
                # 与写回管线口径对齐：仅“声明为泛型”的输出端口需要 OutParam record 表达具体类型。
                out_declared_type_text = ""
                out_declared_map = payload.get("output_port_declared_types")
                if isinstance(out_declared_map, dict):
                    dt = out_declared_map.get(out_port_name)
                    if isinstance(dt, str):
                        out_declared_type_text = dt.strip()
                if (not out_declared_type_text) and (node_def is not None):
                    out_declared_type_text = str(node_def.get_port_type(str(out_port_name), is_input=False)).strip()
                from ugc_file_tools.node_graph_semantics.graph_generater import (
                    is_declared_generic_port_type as _is_declared_generic_port_type,
                )

                is_declared_generic_output = _is_declared_generic_port_type(str(out_declared_type_text))
                if not bool(is_declared_generic_output):
                    continue

                desired = out_types.get(out_port_name)
                desired_text = str(desired).strip() if isinstance(desired, str) else ""
                if (not desired_text) or desired_text == "流程" or ("泛型" in desired_text):
                    continue
                vt = _try_map_port_type_text_to_var_type_int(desired_text)
                if not isinstance(vt, int):
                    outparam_needs_local.append(
                        {
                            "node_id": node_id,
                            "node_title": title,
                            "type_id_int": int(type_id),
                            "out_index": int(out_index),
                            "out_port": out_port_name,
                            "desired_type_text": desired_text,
                            "issue": "OUTPUT_TYPE_NOT_MAPPABLE",
                        }
                    )
                    continue
                required_outparam_templates.append(
                    _OutParamNeed(
                        node_title=str(title),
                        type_id_int=int(type_id),
                        out_index=int(out_index),
                        out_port=str(out_port_name),
                        desired_type_text=str(desired_text),
                        desired_var_type_int=int(vt),
                    )
                )

        # ---- input_constants -> default writeback gaps ----
        for node_id, payload in node_by_id.items():
            title = str(payload.get("title") or "").strip()
            type_id = title_to_type_id.get(title)
            if not isinstance(type_id, int):
                continue
            input_constants = payload.get("input_constants")
            if not isinstance(input_constants, dict):
                continue
            input_port_types = payload.get("input_port_types")
            if not isinstance(input_port_types, dict):
                input_port_types = payload.get("effective_input_types")
            if not isinstance(input_port_types, dict):
                continue
            inputs_value = payload.get("inputs")
            inputs_all = [str(x) for x in inputs_value] if isinstance(inputs_value, list) else []
            node_def = node_defs_by_scope.get(scope, {}).get(str(title))
            data_inputs = _filter_data_ports_by_node_def(ports=inputs_all, node_def=node_def, is_input=True)
            for port_name_raw, raw_value in input_constants.items():
                port_name = str(port_name_raw)
                port_type = str(input_port_types.get(port_name) or "").strip()
                if not port_type or port_type == "流程":
                    continue
                if "泛型" in port_type:
                    continue
                if port_name not in data_inputs:
                    continue
                vt = _try_map_port_type_text_to_var_type_int(port_type)
                if not isinstance(vt, int):
                    input_constant_unknown_port_types.append(
                        {
                            "graph_json": str(json_path),
                            "graph_name": graph_name,
                            "node_title": title,
                            "type_id_int": int(type_id),
                            "port": port_name,
                            "port_type": port_type,
                            "raw_value": raw_value,
                        }
                    )
                    continue

                data_input_slot_index = int(data_inputs.index(port_name))
                record_pin_index = int(
                    map_inparam_pin_index_for_node(
                        node_title=str(title), port_name=str(port_name), slot_index=int(data_input_slot_index)
                    )
                )
                if int(vt) == 27:
                    input_constant_dict_ports.append(
                        {
                            "graph_json": str(json_path),
                            "graph_name": graph_name,
                            "node_title": title,
                            "type_id_int": int(type_id),
                            "port": port_name,
                            "data_input_slot_index": int(data_input_slot_index),
                            "record_pin_index": int(record_pin_index),
                            "port_type": port_type,
                            "raw_value": raw_value,
                        }
                    )
                    continue
                if port_type.endswith("列表") and isinstance(raw_value, str):
                    if not _is_list_constant_string_supported(port_type, raw_value):
                        input_constant_list_string_unsupported.append(
                            {
                                "graph_json": str(json_path),
                                "graph_name": graph_name,
                                "node_title": title,
                                "type_id_int": int(type_id),
                                "port": port_name,
                                "port_type": port_type,
                                "raw_value": raw_value,
                            }
                        )

        per_graph.append(
            {
                "graph_json": str(json_path),
                "graph_name": graph_name,
                "scope": str(scope),
                "nodes_total": int(len(nodes)),
                "titles_unique": int(len(unique_titles)),
                "missing_type_id_mapping_titles": list(sorted(missing_mapping)),
                "ambiguous_title_mappings": list(sorted(ambiguous, key=lambda x: str(x.get("title") or ""))),
                "data_edge_dst_port_not_in_inputs": edge_slot_miss,
                "outparam_needs_local_issues": outparam_needs_local,
            }
        )

    # ===== 构建模板库（与写回管线同口径）=====
    from ugc_file_tools.node_graph_writeback.gil_dump import (
        dump_gil_to_raw_json_object,
        find_graph_entry,
        get_payload_root,
    )
    from ugc_file_tools.node_graph_writeback.template_library import build_template_library

    template_gil_resolved = Path(template_gil_path).resolve()
    if not template_gil_resolved.is_file():
        raise FileNotFoundError(str(template_gil_resolved))

    raw = dump_gil_to_raw_json_object(template_gil_resolved)
    payload_root = get_payload_root(raw)
    entry = find_graph_entry(payload_root, int(template_graph_id_int))
    nodes_value = entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError("template graph entry missing nodes list (entry['3'])")
    template_nodes = [n for n in nodes_value if isinstance(n, dict)]
    if not template_nodes:
        raise ValueError("template graph nodes is empty")

    template_node_id_set: Set[int] = set()
    for n in template_nodes:
        node_id_value = n.get("1")
        if isinstance(node_id_value, list) and node_id_value and isinstance(node_id_value[0], int):
            template_node_id_set.add(int(node_id_value[0]))

    lib = build_template_library(
        template_nodes=template_nodes,
        template_node_id_set=set(int(v) for v in template_node_id_set),
        template_library_dir=(Path(template_library_dir).resolve() if template_library_dir is not None else None),
        effective_base_gil_path=template_gil_resolved,
    )

    covered_type_ids: Set[int] = set(int(k) for k in lib.node_template_by_type_id.keys())
    # data slots: dst_type_id -> {slot_index}
    covered_data_slots: Dict[int, Set[int]] = {
        int(tid): set(int(s) for s in mp.keys())
        for tid, mp in lib.data_link_record_template_by_dst_type_id_and_slot_index.items()
        if isinstance(mp, dict)
    }
    # outparam: type_id -> out_index -> {var_type_int}
    covered_outparam: Dict[int, Dict[int, Set[int]]] = {}
    for tid, by_index in lib.outparam_record_template_by_type_id_and_index_and_var_type.items():
        if not isinstance(by_index, dict):
            continue
        for out_index, by_vt in by_index.items():
            if not isinstance(by_vt, dict):
                continue
            covered_outparam.setdefault(int(tid), {}).setdefault(int(out_index), set()).update(
                set(int(vt) for vt in by_vt.keys() if isinstance(vt, int))
            )

    # ===== gap 计算 =====
    missing_node_templates = sorted(list(required_type_ids_all - covered_type_ids))
    missing_node_templates_human: List[Dict[str, Any]] = []
    for tid in list(missing_node_templates):
        meta = type_id_to_meta.get(int(tid)) or {}
        missing_node_templates_human.append(
            {
                "type_id_int": int(tid),
                "node_name": str(meta.get("node_name") or ""),
                "scope": str(meta.get("scope") or ""),
            }
        )

    missing_data_link_slot_templates: List[Dict[str, Any]] = []
    required_data_slot_total = 0
    for tid, pins in required_data_pins_by_type_id.items():
        for pin_index in sorted(set(int(v) for v in pins)):
            required_data_slot_total += 1
            if int(pin_index) not in covered_data_slots.get(int(tid), set()):
                meta = type_id_to_meta.get(int(tid)) or {}
                example = required_data_pin_examples.get((int(tid), int(pin_index))) or {}
                missing_data_link_slot_templates.append(
                    {
                        "dst_type_id_int": int(tid),
                        # 对齐模板库 key：record pin_index（写回时的 InParam.index）
                        "slot_index": int(pin_index),
                        # 人类可读：尽量写出“哪个节点/哪个端口”（从 GraphModel 记录一个示例）
                        "node_name": str(meta.get("node_name") or ""),
                        "scope": str(meta.get("scope") or ""),
                        "dst_title_example": str(example.get("dst_title") or ""),
                        "dst_port_example": str(example.get("dst_port") or ""),
                        # 可选：端口类型/VarType（供 auto-wire 直接写 record，避免依赖 GraphModel 文件）
                        "dst_port_type_text": str(example.get("dst_port_type_text") or ""),
                        "dst_var_type_int": (
                            int(example.get("dst_var_type_int"))
                            if isinstance(example.get("dst_var_type_int"), int)
                            else None
                        ),
                        "data_input_slot_index_example": example.get("data_input_slot_index"),
                        "record_pin_index": int(pin_index),
                        "example_graph_json": str(example.get("graph_json") or ""),
                        "example_graph_name": str(example.get("graph_name") or ""),
                    }
                )

    missing_outparam_templates: List[Dict[str, Any]] = []
    for need in required_outparam_templates:
        covered_vts = covered_outparam.get(int(need.type_id_int), {}).get(int(need.out_index), set())
        if int(need.desired_var_type_int) not in set(int(v) for v in covered_vts):
            meta = type_id_to_meta.get(int(need.type_id_int)) or {}
            missing_outparam_templates.append(
                {
                    "node_title": need.node_title,
                    "type_id_int": int(need.type_id_int),
                    "out_index": int(need.out_index),
                    "out_port": str(need.out_port),
                    "node_name": str(meta.get("node_name") or ""),
                    "scope": str(meta.get("scope") or ""),
                    "desired_type_text": need.desired_type_text,
                    "desired_var_type_int": int(need.desired_var_type_int),
                }
            )

    report_obj: Dict[str, Any] = {
        "inputs": {
            "template_gil": str(template_gil_resolved),
            "template_graph_id_int": int(template_graph_id_int),
            "template_library_dir": str(Path(template_library_dir).resolve()) if template_library_dir is not None else "",
            "mapping": str(Path(mapping_path).resolve()),
            "graph_generater_root": str(Path(graph_generater_root).resolve()),
            "graph_models": [str(p) for p in graph_json_files],
            "default_scope": str(default_scope_norm),
        },
        "template_library_coverage": {
            "node_template_type_ids_count": int(len(covered_type_ids)),
            "data_link_dst_type_ids_count": int(len(covered_data_slots)),
            "outparam_type_ids_count": int(len(covered_outparam)),
        },
        "graph_models_requirements": {
            "graphs": int(len(per_graph)),
            "required_type_ids_count": int(len(required_type_ids_all)),
            "required_type_ids": sorted(list(required_type_ids_all)),
            "required_data_slot_total": int(required_data_slot_total),
            "required_outparam_templates_total": int(len(required_outparam_templates)),
            "note": "required_data_slot_total 按 record pin_index 计数（对齐写回模板库 key）。动态端口节点会按 pin_rules 做 slot_index→pin_index 映射。",
        },
        "gaps": {
            "missing_type_id_mapping_titles": sorted(list(missing_mapping_titles_all)),
            "missing_type_id_mapping_titles_count": int(len(missing_mapping_titles_all)),
            "ambiguous_title_mappings": [
                {"title": title, "type_ids": sorted(list(type_ids))}
                for title, type_ids in sorted(ambiguous_titles_all.items(), key=lambda kv: kv[0])
            ],
            "ambiguous_title_mappings_count": int(len(ambiguous_titles_all)),
            "missing_node_templates_type_ids": list(missing_node_templates),
            "missing_node_templates_type_ids_count": int(len(missing_node_templates)),
            "missing_node_templates": list(missing_node_templates_human),
            "missing_data_link_slot_templates": list(missing_data_link_slot_templates),
            "missing_data_link_slot_templates_count": int(len(missing_data_link_slot_templates)),
            "missing_outparam_templates": list(missing_outparam_templates),
            "missing_outparam_templates_count": int(len(missing_outparam_templates)),
            "default_value_writeback": {
                "input_constants_dict_ports": list(input_constant_dict_ports),
                "input_constants_dict_ports_count": int(len(input_constant_dict_ports)),
                "input_constants_unknown_port_types": list(input_constant_unknown_port_types),
                "input_constants_unknown_port_types_count": int(len(input_constant_unknown_port_types)),
                "input_constants_list_string_unsupported": list(input_constant_list_string_unsupported),
                "input_constants_list_string_unsupported_count": int(len(input_constant_list_string_unsupported)),
                "note": "当前 input_constants 写回不支持字典常量；列表常量若用字符串表示，仅部分列表类型支持解析。",
            },
        },
        "graphs": list(per_graph),
    }
    return report_obj


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "写回覆盖差异报告：对比 GraphModel(JSON) 需求 vs 当前模板样本库覆盖，输出缺口列表。"
        )
    )
    parser.add_argument("--template-gil", required=True, help="用于写回的 template_gil（与写回脚本参数一致）。")
    parser.add_argument("--template-graph-id", dest="template_graph_id_int", type=int, required=True, help="template_gil 中用于构建模板库的 graph_id_int。")
    parser.add_argument("--template-library-dir", default=None, help="可选：额外样本库目录（递归扫描 *.gil）。")
    parser.add_argument(
        "--mapping",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="node_type_semantic_map.json 路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）。",
    )
    parser.add_argument(
        "--graph-generater-root",
        default=str(repo_root()),
        help="Graph_Generater 仓库根目录（用于加载 NodeDef 做端口/flow 判定与动态端口 pin_index 映射）。",
    )
    parser.add_argument("--default-scope", default="server", help="当 GraphModel 未声明 graph_type 时使用的默认 scope（server/client）。")
    parser.add_argument(
        "--output-json",
        default="graph_writeback_gaps.report.json",
        help="输出报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument(
        "graph_models",
        nargs="+",
        help="GraphModel(JSON) 文件或目录（目录会匹配 *.graph_model.typed*.json / *.graph_model.json）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    template_library_dir = Path(args.template_library_dir).resolve() if args.template_library_dir else None
    if template_library_dir is not None and not template_library_dir.is_dir():
        raise FileNotFoundError(str(template_library_dir))

    mapping_path = Path(args.mapping).resolve()
    if not mapping_path.is_file():
        raise FileNotFoundError(str(mapping_path))

    graph_generater_root = Path(args.graph_generater_root).resolve()
    if not graph_generater_root.is_dir():
        raise FileNotFoundError(str(graph_generater_root))

    report = build_report(
        template_gil_path=Path(args.template_gil),
        template_graph_id_int=int(args.template_graph_id_int),
        template_library_dir=template_library_dir,
        mapping_path=mapping_path,
        graph_generater_root=graph_generater_root,
        default_scope=str(args.default_scope),
        graph_model_paths=list(args.graph_models),
    )

    out_path = resolve_output_file_path_in_out_dir(Path(str(args.output_json)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report.get("gaps") if isinstance(report, dict) else None
    print("================================================================================")
    print("写回覆盖差异报告已生成：")
    print(f"- output: {str(out_path)}")
    if isinstance(summary, dict):
        print("---- summary ----")
        print(f"missing_type_id_mapping_titles_count = {int(summary.get('missing_type_id_mapping_titles_count') or 0)}")
        print(f"ambiguous_title_mappings_count = {int(summary.get('ambiguous_title_mappings_count') or 0)}")
        print(f"missing_node_templates_type_ids_count = {int(summary.get('missing_node_templates_type_ids_count') or 0)}")
        print(f"missing_data_link_slot_templates_count = {int(summary.get('missing_data_link_slot_templates_count') or 0)}")
        print(f"missing_outparam_templates_count = {int(summary.get('missing_outparam_templates_count') or 0)}")
        dv = summary.get('default_value_writeback')
        if isinstance(dv, dict):
            print(f"input_constants_dict_ports_count = {int(dv.get('input_constants_dict_ports_count') or 0)}")
    print("================================================================================")


if __name__ == "__main__":
    main()



