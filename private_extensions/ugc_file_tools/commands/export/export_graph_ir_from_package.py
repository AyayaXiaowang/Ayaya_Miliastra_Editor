from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.node_data_index import load_node_name_by_id_if_exists
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir
from ugc_file_tools.repo_paths import ugc_file_tools_root

def _infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    """
    根据 graph_id 的高位前缀推断节点图类型：
    - 0x40000000: server
    - 0x40800000: client
    """
    masked_value = int(graph_id_int) & 0xFF800000
    if masked_value == 0x40000000:
        return "server"
    if masked_value == 0x40800000:
        return "client"
    return "unknown"


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\\\|?*]')


def _sanitize_filename(name: str, *, max_length: int = 120) -> str:
    text = str(name or "").strip()
    if text == "":
        return "untitled"
    text = _INVALID_FILENAME_CHARS.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > int(max_length):
        text = text[: int(max_length)].rstrip()
    if text == "":
        return "untitled"
    return text


def _ensure_directory(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)


def _write_json_file(target_path: Path, payload: Any) -> None:
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_file(target_path: Path, text: str) -> None:
    target_path.write_text(str(text or ""), encoding="utf-8")


def _collect_utf8_values_from_generic_decoded(python_object: Any) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            utf8_value = value.get("utf8")
            if isinstance(utf8_value, str):
                text = utf8_value.strip()
                if text != "" and text not in seen:
                    seen.add(text)
                    results.append(text)
            for child in value.values():
                walk(child)
            return
        if isinstance(value, list):
            for child in value:
                walk(child)
            return

    walk(python_object)
    return results


def _try_extract_int_from_node(value: Any) -> Optional[int]:
    if not isinstance(value, dict):
        return None
    number = value.get("int")
    if isinstance(number, int):
        return int(number)
    return None


def _get_nested_int(decoded_record: Dict[str, Any], path: Sequence[str]) -> Optional[int]:
    cursor: Any = decoded_record
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return _try_extract_int_from_node(cursor)


def _make_data_port_ref(index_int: int) -> Dict[str, Any]:
    return {"kind": "data", "index": int(index_int)}


def _make_flow_port_ref(group_int: int, branch_int: int) -> Dict[str, Any]:
    return {"kind": "flow", "group": int(group_int), "branch": int(branch_int)}


def _parse_link_edge_from_record(
    decoded_record: Dict[str, Any],
    *,
    current_node_id_int: int,
    node_id_set: set[int],
) -> Optional[Dict[str, Any]]:
    """
    将 record 解码结构解析为“可用的边（edge）”。

    约定（已在 test4 的校准图中验证）：
    - **流程边（flow）**：
      - record 不包含 field_4
      - record 存放在“源节点”上（current_node_id_int 为 src）
      - field_5.message.field_1.int = dst_node_id_int
      - field_1.message.field_1/int + field_1.message.field_2/int 共同编码源端口（用于区分双分支等多出口）
      - field_5.message.field_2.message.field_1/int 编码目标端口（通常为 flow-in）
    - **数据边（data）**：
      - record 包含 field_4.int（本端端口索引）
      - record 存放在“目标节点”上（current_node_id_int 为 dst）
      - field_5.message.field_1.int = src_node_id_int
      - field_5.message.field_2.message.field_1/int 编码对端端口索引（通常为输出端口）

    注意：仍有少量 record 可能引用 node_id 但并非连线（例如其它关系/元数据）；
    本函数只解析命中上述形态的 record，其它情况返回 None。
    """
    other_node_id_int = _get_nested_int(decoded_record, ["field_5", "message", "field_1"])
    if not isinstance(other_node_id_int, int):
        return None
    if other_node_id_int not in node_id_set:
        return None

    local_data_port_index_int = _get_nested_int(decoded_record, ["field_4"])
    remote_port_index_a = _get_nested_int(decoded_record, ["field_5", "message", "field_2", "message", "field_1"])
    remote_port_index_b = _get_nested_int(decoded_record, ["field_5", "message", "field_3", "message", "field_1"])

    # ===== 数据边（目标节点本地含 field_4）=====
    if isinstance(local_data_port_index_int, int):
        src_node_id_int = int(other_node_id_int)
        dst_node_id_int = int(current_node_id_int)

        src_port_index_int = remote_port_index_a if isinstance(remote_port_index_a, int) else remote_port_index_b
        if not isinstance(src_port_index_int, int):
            return None

        return {
            "edge_kind": "data",
            "src_node_id_int": src_node_id_int,
            "src_port_ref": _make_data_port_ref(int(src_port_index_int)),
            "dst_node_id_int": dst_node_id_int,
            "dst_port_ref": _make_data_port_ref(int(local_data_port_index_int)),
            "raw": {
                "record_fields": sorted(key for key in decoded_record.keys() if str(key).startswith("field_")),
                "remote_port_hint_a_int": int(remote_port_index_a) if isinstance(remote_port_index_a, int) else None,
                "remote_port_hint_b_int": int(remote_port_index_b) if isinstance(remote_port_index_b, int) else None,
            },
        }

    # ===== 流程边（源节点本地不含 field_4）=====
    src_flow_group_int = _get_nested_int(decoded_record, ["field_1", "message", "field_1"])
    src_flow_branch_int = _get_nested_int(decoded_record, ["field_1", "message", "field_2"])
    dst_flow_group_int = remote_port_index_a if isinstance(remote_port_index_a, int) else remote_port_index_b
    dst_flow_branch_int = _get_nested_int(decoded_record, ["field_5", "message", "field_2", "message", "field_2"])

    if not isinstance(src_flow_group_int, int):
        return None
    if not isinstance(dst_flow_group_int, int):
        return None

    src_node_id_int = int(current_node_id_int)
    dst_node_id_int = int(other_node_id_int)

    return {
        "edge_kind": "flow",
        "src_node_id_int": src_node_id_int,
        "src_port_ref": _make_flow_port_ref(
            int(src_flow_group_int),
            int(src_flow_branch_int) if isinstance(src_flow_branch_int, int) else 0,
        ),
        "dst_node_id_int": dst_node_id_int,
        "dst_port_ref": _make_flow_port_ref(
            int(dst_flow_group_int),
            int(dst_flow_branch_int) if isinstance(dst_flow_branch_int, int) else 0,
        ),
        "raw": {
            "record_fields": sorted(key for key in decoded_record.keys() if str(key).startswith("field_")),
            "remote_port_hint_a_int": int(remote_port_index_a) if isinstance(remote_port_index_a, int) else None,
            "remote_port_hint_b_int": int(remote_port_index_b) if isinstance(remote_port_index_b, int) else None,
        },
    }


def _extract_port_index_int_from_record(decoded_record: Dict[str, Any]) -> Optional[int]:
    """
    尝试从 record 解码结构中提取“端口索引”：
    - 先尝试 field_7.int（在部分自研节点/节点定义中更常见）
    - 再尝试 field_4.int（在部分内置节点图 record 结构中更常见）
    """
    port_index_int = _get_nested_int(decoded_record, ["field_7"])
    if isinstance(port_index_int, int):
        return int(port_index_int)
    fallback_port_index_int = _get_nested_int(decoded_record, ["field_4"])
    if isinstance(fallback_port_index_int, int):
        return int(fallback_port_index_int)
    return None


def _load_json_file_as_object(file_path: Path) -> Any:
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def _load_pyugc_node_def_name_by_id(*, package_root: Path) -> Dict[int, str]:
    """
    读取项目存档导出的 pyugc_node_defs_index.json，将 node_def_id_int 映射到 node_name。
    用途：为 16106127xx 这类“自研节点定义ID”提供稳定的人类可读名称。
    """
    index_path = Path(package_root).resolve() / "节点图" / "原始解析" / "pyugc_node_defs_index.json"
    if not index_path.is_file():
        return {}

    index_object = _load_json_file_as_object(index_path)
    if not isinstance(index_object, list):
        return {}

    mapping: Dict[int, str] = {}
    for entry in index_object:
        if not isinstance(entry, dict):
            continue
        node_def_id_value = entry.get("node_def_id_int")
        node_name_value = entry.get("node_name")
        if not isinstance(node_def_id_value, int):
            continue
        node_name = str(node_name_value or "").strip()
        if node_name == "":
            continue
        mapping[int(node_def_id_value)] = node_name
    return mapping


def _load_signal_node_def_index(*, package_root: Path) -> Dict[int, Dict[str, Any]]:
    """
    读取项目存档导出的信号节点定义索引，将 node_def_id_int 映射到信号信息：
    - role: send/listen/send_to_server
    - signal_index_int/signal_name
    - signal_output: 指向单个信号定义 JSON

    注意：该索引由 `gil_package_exporter/signal_exporter.py` 生成；若不存在则返回空。
    """
    index_path = Path(package_root).resolve() / "管理配置" / "信号" / "signal_node_defs_index.json"
    if not index_path.is_file():
        return {}

    index_object = _load_json_file_as_object(index_path)
    if not isinstance(index_object, list):
        return {}

    mapping: Dict[int, Dict[str, Any]] = {}
    for entry in index_object:
        if not isinstance(entry, dict):
            continue
        node_def_id_value = entry.get("node_def_id_int")
        if not isinstance(node_def_id_value, int):
            continue
        mapping[int(node_def_id_value)] = dict(entry)
    return mapping


def _simplify_signal_payload(signal_payload: Dict[str, Any]) -> Dict[str, Any]:
    params_value = signal_payload.get("params")
    simplified_params: List[Dict[str, Any]] = []
    if isinstance(params_value, list):
        for param in params_value:
            if not isinstance(param, dict):
                continue
            simplified_params.append(
                {
                    "param_index": param.get("param_index"),
                    "param_name": param.get("param_name"),
                    "type_id": param.get("type_id"),
                    "type_name": param.get("type_name"),
                    "order_int": param.get("order_int"),
                    "port_index_by_role": param.get("port_index_by_role"),
                }
            )

    return {
        "signal_index_int": signal_payload.get("signal_index_int"),
        "signal_name": signal_payload.get("signal_name"),
        "node_def_ids": signal_payload.get("node_def_ids"),
        "params": simplified_params,
    }


def _load_node_type_semantic_map() -> Dict[int, Dict[str, Any]]:
    """
    从 ugc_file_tools/graph_ir/node_type_semantic_map.json 读取“内置节点类型语义映射”。
    若文件不存在则返回空映射。
    """
    mapping_path = ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"
    if not mapping_path.is_file():
        return {}

    mapping_object = _load_json_file_as_object(mapping_path)
    if not isinstance(mapping_object, dict):
        return {}

    result: Dict[int, Dict[str, Any]] = {}
    for key, value in mapping_object.items():
        try_parse_int = None
        if isinstance(key, int):
            try_parse_int = int(key)
        elif isinstance(key, str) and key.strip().isdigit():
            try_parse_int = int(key.strip())
        if not isinstance(try_parse_int, int):
            continue
        if not isinstance(value, dict):
            continue
        result[int(try_parse_int)] = dict(value)
    return result


def _build_node_type_name_hint(
    *,
    node_type_id_int: Optional[int],
    node_def_name_by_id: Dict[int, str],
    semantic_map_by_type_id: Dict[int, Dict[str, Any]],
    node_data_node_name_by_id: Dict[int, str],
) -> Tuple[str, str]:
    """
    返回 (node_type_name_hint, node_type_semantic_id_hint)。
    优先级：
    1) pyugc node defs（自研节点）：
       - node_type_id_int 命中 node_def_name_by_id → 使用 node_def_name
    2) 维护的语义映射表（内置节点）：
       - node_type_id_int 命中 semantic_map → 使用 graph_generater_node_name / semantic_id
    3) 节点数据索引（node_data/index.json）：
       - node_type_id_int 命中 node_data/index.json → 使用 safe node name（无 semantic_id）
    """
    if not isinstance(node_type_id_int, int):
        return "", ""

    node_def_name = node_def_name_by_id.get(int(node_type_id_int))
    if isinstance(node_def_name, str) and node_def_name.strip() != "":
        return node_def_name.strip(), ""

    semantic_entry = semantic_map_by_type_id.get(int(node_type_id_int))
    if isinstance(semantic_entry, dict):
        node_name_hint = str(semantic_entry.get("graph_generater_node_name") or "").strip()
        semantic_id_hint = str(semantic_entry.get("semantic_id") or "").strip()
        if node_name_hint != "" or semantic_id_hint != "":
            return node_name_hint, semantic_id_hint

    node_data_name = node_data_node_name_by_id.get(int(node_type_id_int))
    if isinstance(node_data_name, str) and node_data_name.strip() != "":
        return node_data_name.strip(), ""

    return "", ""


def export_readable_graph_ir_for_package_root(
    package_root: Path,
    *,
    output_dir: Optional[Path] = None,
    write_markdown: bool = True,
) -> Dict[str, Any]:
    package_root_path = Path(package_root).resolve()
    if not package_root_path.is_dir():
        raise FileNotFoundError(f"package root not found: {str(package_root_path)!r}")

    raw_graphs_dir = package_root_path / "节点图" / "原始解析" / "pyugc_graphs"
    if not raw_graphs_dir.is_dir():
        raise FileNotFoundError(f"pyugc_graphs dir not found: {str(raw_graphs_dir)!r}")

    node_def_name_by_id = _load_pyugc_node_def_name_by_id(package_root=package_root_path)
    semantic_map_by_type_id = _load_node_type_semantic_map()
    node_data_node_name_by_id = load_node_name_by_id_if_exists()
    signal_node_def_index = _load_signal_node_def_index(package_root=package_root_path)
    signal_payload_cache: Dict[str, Dict[str, Any]] = {}

    # 统一输出到 ugc_file_tools/out 下，避免把“可再生产物”落到项目存档目录里
    readable_root = resolve_output_dir_path_in_out_dir(
        Path(output_dir) if output_dir is not None else Path(f"graph_ir_{package_root_path.name}")
    )
    graphs_json_dir = readable_root / "graphs"
    graphs_markdown_dir = readable_root / "graphs_markdown"
    _ensure_directory(graphs_json_dir)
    if write_markdown:
        _ensure_directory(graphs_markdown_dir)

    exported_index: List[Dict[str, Any]] = []
    node_type_profiles: Dict[str, Dict[str, Any]] = {}

    for graph_path in sorted(raw_graphs_dir.glob("graph_*.json"), key=lambda p: p.name.casefold()):
        graph_payload = json.loads(graph_path.read_text(encoding="utf-8"))
        if not isinstance(graph_payload, dict):
            continue

        graph_id_value = graph_payload.get("graph_id_int")
        graph_name = str(graph_payload.get("graph_name") or "").strip()
        source_pyugc_path = str(graph_payload.get("source_pyugc_path") or "").strip()
        decoded_nodes = graph_payload.get("decoded_nodes")
        if not isinstance(graph_id_value, int) or not isinstance(decoded_nodes, list):
            continue
        graph_id_int = int(graph_id_value)
        graph_scope = _infer_graph_scope_from_id_int(graph_id_int)

        node_id_set: set[int] = set()
        for node in decoded_nodes:
            if isinstance(node, dict) and isinstance(node.get("node_id_int"), int):
                node_id_set.add(int(node.get("node_id_int")))

        node_items: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        graph_utf8_values: List[str] = []
        graph_utf8_seen: set[str] = set()

        for node in decoded_nodes:
            if not isinstance(node, dict):
                continue
            node_id_value = node.get("node_id_int")
            if not isinstance(node_id_value, int):
                continue
            node_id_int = int(node_id_value)

            pos_object = node.get("pos")
            pos_x = float(pos_object.get("x", 0.0) or 0.0) if isinstance(pos_object, dict) else 0.0
            pos_y = float(pos_object.get("y", 0.0) or 0.0) if isinstance(pos_object, dict) else 0.0

            data_2_decoded = (node.get("data_2") or {}).get("decoded") if isinstance(node.get("data_2"), dict) else None
            data_3_decoded = (node.get("data_3") or {}).get("decoded") if isinstance(node.get("data_3"), dict) else None
            data_2_type_id = None
            data_3_type_id = None
            if isinstance(data_2_decoded, dict):
                data_2_type_id = _try_extract_int_from_node(data_2_decoded.get("field_5"))
            if isinstance(data_3_decoded, dict):
                data_3_type_id = _try_extract_int_from_node(data_3_decoded.get("field_5"))

            node_type_name_hint, node_type_semantic_id_hint = _build_node_type_name_hint(
                node_type_id_int=data_2_type_id,
                node_def_name_by_id=node_def_name_by_id,
                semantic_map_by_type_id=semantic_map_by_type_id,
                node_data_node_name_by_id=node_data_node_name_by_id,
            )

            signal_info: Optional[Dict[str, Any]] = None
            if isinstance(data_2_type_id, int):
                signal_node_entry = signal_node_def_index.get(int(data_2_type_id))
                if isinstance(signal_node_entry, dict):
                    signal_output = signal_node_entry.get("signal_output")
                    if isinstance(signal_output, str) and signal_output.strip() != "":
                        cached = signal_payload_cache.get(signal_output)
                        if cached is None:
                            signal_payload_path = package_root_path / Path(signal_output)
                            loaded = _load_json_file_as_object(signal_payload_path)
                            cached = loaded if isinstance(loaded, dict) else {}
                            signal_payload_cache[signal_output] = cached
                        signal_info = {
                            "role": signal_node_entry.get("role"),
                            **_simplify_signal_payload(cached if isinstance(cached, dict) else {}),
                        }

            node_type_detail_name_hint = node_type_name_hint
            if isinstance(signal_info, dict):
                signal_name_hint = str(signal_info.get("signal_name") or "").strip()
                if signal_name_hint != "" and node_type_detail_name_hint != "":
                    node_type_detail_name_hint = f"{node_type_detail_name_hint}({signal_name_hint})"

            records = node.get("records")
            record_summaries: List[Dict[str, Any]] = []
            node_utf8_values: List[str] = []
            node_utf8_seen: set[str] = set()
            node_port_indices: List[int] = []
            node_port_index_seen: set[int] = set()

            if isinstance(records, list):
                for record_index, record in enumerate(records):
                    if not isinstance(record, dict):
                        continue
                    decoded_record = record.get("decoded")
                    if not isinstance(decoded_record, dict):
                        continue

                    port_index_int = _extract_port_index_int_from_record(decoded_record)
                    if isinstance(port_index_int, int) and port_index_int not in node_port_index_seen:
                        node_port_index_seen.add(port_index_int)
                        node_port_indices.append(port_index_int)

                    utf8_values = _collect_utf8_values_from_generic_decoded(decoded_record)
                    for text in utf8_values:
                        if text not in node_utf8_seen:
                            node_utf8_seen.add(text)
                            node_utf8_values.append(text)
                        if text not in graph_utf8_seen:
                            graph_utf8_seen.add(text)
                            graph_utf8_values.append(text)

                    parsed_edge = _parse_link_edge_from_record(
                        decoded_record,
                        current_node_id_int=node_id_int,
                        node_id_set=node_id_set,
                    )
                    if parsed_edge is not None:
                        edge_with_meta: Dict[str, Any] = {
                            **parsed_edge,
                            "record_index": int(record_index),
                        }
                        edges.append(edge_with_meta)

                    record_summaries.append(
                        {
                            "record_index": int(record_index),
                            "port_index_int": int(port_index_int) if isinstance(port_index_int, int) else None,
                            "utf8_values": utf8_values,
                            "edge": (
                                {
                                    "edge_kind": str(parsed_edge.get("edge_kind")),
                                    "src_node_id_int": int(parsed_edge.get("src_node_id_int")),
                                    "dst_node_id_int": int(parsed_edge.get("dst_node_id_int")),
                                    "src_port_ref": parsed_edge.get("src_port_ref"),
                                    "dst_port_ref": parsed_edge.get("dst_port_ref"),
                                }
                                if isinstance(parsed_edge, dict)
                                else None
                            ),
                        }
                    )

            node_items.append(
                {
                    "node_id_int": node_id_int,
                    "pos": {"x": pos_x, "y": pos_y},
                    "data_2_type_id_int": data_2_type_id,
                    "data_3_type_id_int": data_3_type_id,
                    "node_type_name_hint": node_type_name_hint,
                    "node_type_detail_name_hint": node_type_detail_name_hint,
                    "node_type_semantic_id_hint": node_type_semantic_id_hint,
                    "signal": signal_info,
                    "record_count": len(record_summaries),
                    "port_index_values": sorted(node_port_indices),
                    "utf8_values": node_utf8_values,
                    "records": record_summaries,
                }
            )

            # 聚合节点类型画像（以 data_2_type_id_int 作为“节点类型ID”）
            if isinstance(data_2_type_id, int):
                type_key = str(int(data_2_type_id))
                profile = node_type_profiles.get(type_key)
                if profile is None:
                    profile = {
                        "node_type_id_int": int(data_2_type_id),
                        "graph_scopes": [],
                        "graph_ids": [],
                        "node_count": 0,
                        "record_count_total": 0,
                        "record_count_max": 0,
                        "port_index_values": [],
                        "utf8_samples": [],
                    }
                    node_type_profiles[type_key] = profile

                profile["node_count"] = int(profile.get("node_count", 0) or 0) + 1
                profile["record_count_total"] = int(profile.get("record_count_total", 0) or 0) + len(record_summaries)
                profile["record_count_max"] = max(int(profile.get("record_count_max", 0) or 0), len(record_summaries))
                existing_graph_ids = set(int(value) for value in (profile.get("graph_ids") or []) if isinstance(value, int))
                if graph_id_int not in existing_graph_ids:
                    profile["graph_ids"] = list(profile.get("graph_ids") or []) + [int(graph_id_int)]
                existing_scopes = set(str(value) for value in (profile.get("graph_scopes") or []) if isinstance(value, str))
                if graph_scope not in existing_scopes:
                    profile["graph_scopes"] = list(profile.get("graph_scopes") or []) + [graph_scope]

                existing_ports = set(int(value) for value in (profile.get("port_index_values") or []) if isinstance(value, int))
                for port_index in node_port_indices:
                    if port_index not in existing_ports:
                        existing_ports.add(port_index)
                profile["port_index_values"] = sorted(existing_ports)

                existing_utf8 = set(str(value) for value in (profile.get("utf8_samples") or []) if isinstance(value, str))
                for sample_text in node_utf8_values:
                    if sample_text in existing_utf8:
                        continue
                    existing_utf8.add(sample_text)
                    if len(existing_utf8) >= 48:
                        break
                profile["utf8_samples"] = list(existing_utf8)[:48]
                if node_type_name_hint:
                    profile.setdefault("node_type_name_hint", node_type_name_hint)
                if node_type_semantic_id_hint:
                    profile.setdefault("node_type_semantic_id_hint", node_type_semantic_id_hint)

        graph_ir: Dict[str, Any] = {
            "schema_version": 3,
            "graph_id_int": graph_id_int,
            "graph_name": graph_name,
            "graph_scope": graph_scope,
            "source_pyugc_path": source_pyugc_path,
            "source_pyugc_graph": str(graph_path.relative_to(package_root_path)).replace("\\", "/"),
            "node_count": len(node_items),
            "nodes": node_items,
            "edges": edges,
            "utf8_values": graph_utf8_values,
            "node_type_semantic_map_source": "ugc_file_tools/graph_ir/node_type_semantic_map.json",
            "node_type_name_hint_sources": [
                "pyugc_node_defs_index.json",
                "ugc_file_tools/graph_ir/node_type_semantic_map.json",
                "ugc_file_tools/node_data/index.json (if exists)",
            ],
        }

        output_file_stem = _sanitize_filename(f"graph_ir_{graph_id_int}_{graph_name}", max_length=140)
        json_output_path = graphs_json_dir / f"{output_file_stem}.json"
        _write_json_file(json_output_path, graph_ir)

        markdown_output_path = graphs_markdown_dir / f"{output_file_stem}.md"
        if write_markdown:
            markdown_lines: List[str] = []
            markdown_lines.append(f"## 节点图 IR：{graph_name}")
            markdown_lines.append("")
            markdown_lines.append(f"- graph_id_int: {graph_id_int}")
            markdown_lines.append(f"- scope: {graph_scope}")
            markdown_lines.append(f"- node_count: {len(node_items)}")
            markdown_lines.append(f"- raw_pyugc_graph: `{graph_ir['source_pyugc_graph']}`")
            if source_pyugc_path:
                markdown_lines.append(f"- source_pyugc_path: `{source_pyugc_path}`")
            if graph_utf8_values:
                preview_text = "，".join(graph_utf8_values[:24])
                markdown_lines.append(f"- utf8_samples: {preview_text}")
            markdown_lines.append("")
            markdown_lines.append("### 节点列表（摘要）")
            markdown_lines.append("")

            for node_item in sorted(node_items, key=lambda x: int(x.get("node_id_int", 0))):
                node_id_int = int(node_item.get("node_id_int", 0))
                type_2 = node_item.get("data_2_type_id_int")
                type_3 = node_item.get("data_3_type_id_int")
                type_name_hint = str(node_item.get("node_type_name_hint") or "").strip()
                record_count = int(node_item.get("record_count", 0) or 0)
                ports_text = ""
                port_index_values = node_item.get("port_index_values") or []
                if port_index_values:
                    ports_text = f", ports={port_index_values}"
                utf8_preview = "，".join((node_item.get("utf8_values") or [])[:12])
                markdown_lines.append(
                    f"- node {node_id_int}: type2={type_2}"
                    + (f"({type_name_hint})" if type_name_hint else "")
                    + f", type3={type_3}, records={record_count}"
                    + ports_text
                    + (f", utf8={utf8_preview}" if utf8_preview else "")
                )

            if edges:
                markdown_lines.append("")
                markdown_lines.append("### 连线（edges）")
                markdown_lines.append("")
                for edge in edges[:200]:
                    markdown_lines.append(
                        f"- {edge.get('edge_kind')}: {edge.get('src_node_id_int')}:{edge.get('src_port_ref')} -> "
                        f"{edge.get('dst_node_id_int')}:{edge.get('dst_port_ref')} (record={edge.get('record_index')})"
                    )

            _write_text_file(markdown_output_path, "\n".join(markdown_lines) + "\n")

        exported_index.append(
            {
                "graph_id_int": graph_id_int,
                "graph_name": graph_name,
                "graph_scope": graph_scope,
                "node_count": len(node_items),
                "utf8_count": len(graph_utf8_values),
                "edges_count": len(edges),
                "source_pyugc_graph": graph_ir["source_pyugc_graph"],
                # 输出强制落盘到 ugc_file_tools/out 下，不属于 package_root 的子路径：因此索引里使用相对 readable_root 的路径
                "output_ir_json": str(json_output_path.relative_to(readable_root)).replace("\\", "/"),
                "output_ir_markdown": str(markdown_output_path.relative_to(readable_root)).replace("\\", "/")
                if write_markdown
                else "",
            }
        )

    index_path = readable_root / "graphs_ir_index.json"
    _write_json_file(index_path, sorted(exported_index, key=lambda item: int(item.get("graph_id_int", 0))))

    node_types_index_path = readable_root / "node_types_index.json"
    node_types_rows = sorted(
        node_type_profiles.values(),
        key=lambda row: (-int(row.get("node_count", 0) or 0), int(row.get("node_type_id_int", 0) or 0)),
    )
    _write_json_file(node_types_index_path, node_types_rows)

    def _write_directory_claude(*, directory: Path, purpose_lines: List[str], status_lines: List[str]) -> None:
        lines: List[str] = []
        lines.append("## 目录用途")
        lines.extend(purpose_lines)
        lines.append("")
        lines.append("## 当前状态")
        lines.extend(status_lines)
        lines.append("")
        lines.append("## 注意事项")
        lines.append("- 本目录不记录修改历史，仅保持用途/状态/注意事项的实时描述。")
        lines.append("")
        lines.append("---")
        lines.append("注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。")
        lines.append("")
        _write_text_file(directory / "claude.md", "\n".join(lines))

    claude_path = readable_root / "claude.md"
    claude_lines: List[str] = []
    claude_lines.append("## 目录用途")
    claude_lines.append("- 存放从 `节点图/原始解析/pyugc_graphs/` 导出的“可读节点图 IR”（JSON/Markdown），用于人工分析与后续语义映射。")
    claude_lines.append("")
    claude_lines.append("## 当前状态")
    claude_lines.append(f"- 当前包含 {len(exported_index)} 张节点图的 IR 导出结果。")
    claude_lines.append("- `graphs/`：每张图的 JSON IR（包含 nodes/records/utf8/edges）。")
    if write_markdown:
        claude_lines.append("- `graphs_markdown/`：每张图的 Markdown 摘要（便于阅读）。")
    claude_lines.append("- `graphs_ir_index.json`：图列表索引。")
    claude_lines.append("- `node_types_index.json`：按“节点类型ID（data_2_type_id_int）”聚合的画像索引（node_count/ports/utf8_samples 等）。")
    claude_lines.append("")
    claude_lines.append("## 注意事项")
    claude_lines.append("- IR 为“结构级别”的可读结构：edges 会解析为 flow/data 两类，并输出端口引用（index 或 flow group/branch）。")
    claude_lines.append("- record 的端口索引优先取 `field_7.int`，未命中时回退取 `field_4.int`（用于兼容不同 record 结构）。")
    claude_lines.append("- 端口“命名化”（port_index→端口名）仍需要结合节点语义映射表与更多校准样本逐步完善。")
    claude_lines.append("- 本目录不记录修改历史，仅保持用途/状态/注意事项的实时描述。")
    claude_lines.append("")
    claude_lines.append("---")
    claude_lines.append("注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。")
    claude_lines.append("")
    _write_text_file(claude_path, "\n".join(claude_lines))

    _write_directory_claude(
        directory=graphs_json_dir,
        purpose_lines=["- 存放每张节点图的 JSON IR 文件。"],
        status_lines=[f"- 当前包含 {len(exported_index)} 个 JSON IR 文件。"],
    )
    if write_markdown:
        _write_directory_claude(
            directory=graphs_markdown_dir,
            purpose_lines=["- 存放每张节点图的 Markdown 摘要（从 JSON IR 生成）。"],
            status_lines=[f"- 当前包含 {len(exported_index)} 个 Markdown 文件。"],
        )

    return {
        "package_root": str(package_root_path),
        "raw_graphs_dir": str(raw_graphs_dir),
        "output_dir": str(readable_root),
        "graphs_count": len(exported_index),
        "index": str(index_path.relative_to(readable_root)).replace("\\", "/"),
        "node_types_index": str(node_types_index_path.relative_to(readable_root)).replace("\\", "/"),
    }


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="从项目存档的 pyugc_graphs 导出“可读节点图 IR”（JSON/Markdown）。",
    )
    argument_parser.add_argument(
        "--package-root",
        dest="package_root",
        required=True,
        help="项目存档目录（例如 Graph_Generater/assets/资源库/项目存档/test2）",
    )
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="",
        help="可选：输出目录（默认写入到 <package>/节点图/可读解析/）",
    )
    argument_parser.add_argument(
        "--no-markdown",
        dest="no_markdown",
        action="store_true",
        help="仅导出 JSON，不生成 Markdown 摘要。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    output_dir_text = str(arguments.output_dir or "").strip()
    output_dir = Path(output_dir_text) if output_dir_text != "" else None

    result = export_readable_graph_ir_for_package_root(
        Path(arguments.package_root),
        output_dir=output_dir,
        write_markdown=(not bool(arguments.no_markdown)),
    )
    print("=" * 80)
    print("已完成节点图 IR 导出：")
    print(f"- package_root: {result.get('package_root')}")
    print(f"- raw_graphs_dir: {result.get('raw_graphs_dir')}")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- graphs_count: {result.get('graphs_count')}")
    print(f"- index: {result.get('index')}")
    print(f"- node_types_index: {result.get('node_types_index')}")
    print("=" * 80)


if __name__ == "__main__":
    main()




