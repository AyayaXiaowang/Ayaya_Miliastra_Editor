from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .claude_files import _ensure_claude_for_directory
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file


@dataclass(frozen=True, slots=True)
class PyugcNodeGraphRecord:
    graph_id_int: int
    graph_name: str
    source_pyugc_path: str
    graph_object: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class PyugcNodeDefRecord:
    node_def_id_int: int
    node_name: str
    source_pyugc_path: str
    node_def_object: Dict[str, Any]


def _decode_base64_to_generic_python_object(base64_text: str) -> Dict[str, Any]:
    decoded_bytes = base64.b64decode(base64_text)
    decoded_object = decode_bytes_to_python(decoded_bytes)
    return {
        "base64": base64_text,
        "byte_size": len(decoded_bytes),
        "decoded": decoded_object,
    }


def _walk_with_path(python_object: Any, path_parts: Optional[List[str]] = None) -> List[Tuple[List[str], Any]]:
    """
    返回 (path_parts, value) 扁平列表，供“按结构模式”定位。

    注意：
    - 该方法用于离线导出（解析脚本），不追求最小开销；
    - path_parts 使用与现有输出一致的风格：dict key 直接追加；list 用 [i]。
    """
    collected: List[Tuple[List[str], Any]] = []
    current_path_parts = path_parts if path_parts is not None else []

    if isinstance(python_object, dict):
        collected.append((current_path_parts, python_object))
        for key, child in python_object.items():
            collected.extend(_walk_with_path(child, current_path_parts + [str(key)]))
        return collected

    if isinstance(python_object, list):
        collected.append((current_path_parts, python_object))
        for index, child in enumerate(python_object):
            collected.extend(_walk_with_path(child, current_path_parts + [f"[{index}]"]))
        return collected

    collected.append((current_path_parts, python_object))
    return collected


def _find_pyugc_node_graph_records(pyugc_object: Any) -> List[PyugcNodeGraphRecord]:
    """
    从 pyugc dump 中定位“节点图定义”结构：

    graph_object = {
      "1": [ { "1@int":..., "2@int":..., "3@int":..., "5@int": graph_id_int } ],
      "2": [ "图名" ],
      "3": [ node, node, ... ],
      ...
    }
    """
    found_by_id: Dict[int, PyugcNodeGraphRecord] = {}

    for path_parts, value in _walk_with_path(pyugc_object):
        if not isinstance(value, dict):
            continue

        meta_list = value.get("1")
        name_list = value.get("2")
        nodes_list = value.get("3")

        if not (isinstance(meta_list, list) and meta_list and isinstance(meta_list[0], dict)):
            continue
        if not (isinstance(name_list, list) and name_list and isinstance(name_list[0], str)):
            continue
        if not isinstance(nodes_list, list):
            continue

        graph_id_value = meta_list[0].get("5@int")
        if not isinstance(graph_id_value, int):
            continue
        graph_id_int = int(graph_id_value)

        if graph_id_int in found_by_id:
            continue

        graph_name = name_list[0].strip()
        source_path_text = "/".join(path_parts)
        found_by_id[graph_id_int] = PyugcNodeGraphRecord(
            graph_id_int=graph_id_int,
            graph_name=graph_name,
            source_pyugc_path=source_path_text,
            graph_object=value,
        )

    return sorted(found_by_id.values(), key=lambda record: record.graph_id_int)


def _find_pyugc_node_def_records(pyugc_object: Any) -> List[PyugcNodeDefRecord]:
    """
    从 pyugc dump 中定位“节点定义（节点库条目）”结构：

    wrapper = { "1": node_def_object }
    node_def_object 中包含：
    - 200@string: 节点名
    - 4/1/5@int: 节点定义ID（通常为 0x60000000 + index）
    """
    found_by_id: Dict[int, PyugcNodeDefRecord] = {}

    for path_parts, value in _walk_with_path(pyugc_object):
        if not isinstance(value, dict):
            continue
        inner = value.get("1")
        if not isinstance(inner, dict):
            continue

        node_name_value = inner.get("200@string")
        if not isinstance(node_name_value, str):
            continue
        node_name = node_name_value.strip()

        meta_root = inner.get("4")
        meta_1 = meta_root.get("1") if isinstance(meta_root, dict) else None
        node_def_id_value = meta_1.get("5@int") if isinstance(meta_1, dict) else None
        if not isinstance(node_def_id_value, int):
            continue
        node_def_id_int = int(node_def_id_value)

        if node_def_id_int in found_by_id:
            continue

        source_path_text = "/".join(path_parts + ["1"])
        found_by_id[node_def_id_int] = PyugcNodeDefRecord(
            node_def_id_int=node_def_id_int,
            node_name=node_name,
            source_pyugc_path=source_path_text,
            node_def_object=inner,
        )

    return sorted(found_by_id.values(), key=lambda record: record.node_def_id_int)


def list_pyugc_node_graphs(pyugc_object: Any) -> List[Dict[str, Any]]:
    """
    列出 pyugc dump 中定位到的“节点图定义”清单（不落盘）。

    用途：UI/工具在“选择性导入/导出”前展示可选图列表。
    """
    out: List[Dict[str, Any]] = []
    for record in _find_pyugc_node_graph_records(pyugc_object):
        out.append(
            {
                "graph_id_int": int(record.graph_id_int),
                "graph_name": str(record.graph_name),
                "source_pyugc_path": str(record.source_pyugc_path),
            }
        )
    return out


def export_pyugc_node_graphs_and_node_defs(
    *,
    pyugc_object: Any,
    output_package_root: Path,
    selected_graph_id_ints: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """
    从 pyugc dump 中导出：
    - 节点图：节点图/原始解析/pyugc_graphs/ + pyugc_graphs_index.json
    - 节点定义：节点图/原始解析/pyugc_node_defs/ + pyugc_node_defs_index.json

    目标：
    - 让“节点图定义”与“节点实例内 base64 子结构”可被程序稳定识别与后续语义映射；
    - 不强行生成 Graph_Generater 可执行 Graph Code（该步骤需要进一步的节点/端口语义对齐）。
    """
    node_graph_raw_root = output_package_root / "节点图" / "原始解析"
    pyugc_graphs_directory = node_graph_raw_root / "pyugc_graphs"
    pyugc_node_defs_directory = node_graph_raw_root / "pyugc_node_defs"
    _ensure_directory(pyugc_graphs_directory)
    _ensure_directory(pyugc_node_defs_directory)
    _ensure_claude_for_directory(pyugc_graphs_directory, purpose="存放从 pyugc dump 直接定位到的“节点图定义”原始结构与通用解码结果。")
    _ensure_claude_for_directory(pyugc_node_defs_directory, purpose="存放从 pyugc dump 直接定位到的“节点库/节点定义条目”原始结构。")

    graph_records = _find_pyugc_node_graph_records(pyugc_object)
    node_def_records = _find_pyugc_node_def_records(pyugc_object)

    selected_graph_id_set: Optional[set[int]] = None
    if selected_graph_id_ints is not None:
        selected_graph_id_set = {int(x) for x in list(selected_graph_id_ints)}
        available = {int(r.graph_id_int) for r in list(graph_records)}
        missing = sorted([gid for gid in selected_graph_id_set if gid not in available])
        if missing:
            raise ValueError(f"selected_graph_id_ints 中存在无法定位的 graph_id_int：{missing}")
        graph_records = [r for r in list(graph_records) if int(r.graph_id_int) in selected_graph_id_set]

    exported_graph_index: List[Dict[str, Any]] = []
    exported_node_def_index: List[Dict[str, Any]] = []

    for record in graph_records:
        file_stem = _sanitize_filename(f"graph_{record.graph_id_int}_{record.graph_name}", max_length=120)
        output_path = pyugc_graphs_directory / f"{file_stem}.json"

        decoded_nodes: List[Dict[str, Any]] = []
        raw_nodes = record.graph_object.get("3")
        if isinstance(raw_nodes, list):
            for node_object in raw_nodes:
                if not isinstance(node_object, dict):
                    continue

                node_id_value = None
                node_id_list = node_object.get("1")
                if isinstance(node_id_list, list) and node_id_list and isinstance(node_id_list[0], int):
                    node_id_value = int(node_id_list[0])

                decoded_2 = None
                data_2_text = node_object.get("2@data")
                if isinstance(data_2_text, str) and data_2_text:
                    decoded_2 = _decode_base64_to_generic_python_object(data_2_text)

                decoded_3 = None
                data_3_text = node_object.get("3@data")
                if isinstance(data_3_text, str) and data_3_text:
                    decoded_3 = _decode_base64_to_generic_python_object(data_3_text)

                decoded_records: List[Dict[str, Any]] = []
                record_list = node_object.get("4")
                if isinstance(record_list, list):
                    for record_text in record_list:
                        if not isinstance(record_text, str) or record_text == "":
                            continue
                        decoded_records.append(_decode_base64_to_generic_python_object(record_text))

                extra_fields: Dict[str, Any] = {}
                for key, value in node_object.items():
                    if key in {"1", "2@data", "3@data", "4", "5@float", "6@float"}:
                        continue
                    extra_fields[str(key)] = value

                decoded_nodes.append(
                    {
                        "node_id_int": node_id_value,
                        "pos": {
                            "x": float(node_object.get("5@float", 0.0) or 0.0),
                            "y": float(node_object.get("6@float", 0.0) or 0.0),
                        },
                        "data_2": decoded_2,
                        "data_3": decoded_3,
                        "records": decoded_records,
                        "extra_fields": extra_fields,
                    }
                )

        graph_payload: Dict[str, Any] = {
            "graph_id_int": record.graph_id_int,
            "graph_name": record.graph_name,
            "source_pyugc_path": record.source_pyugc_path,
            "node_count": len(decoded_nodes),
            "decoded_nodes": decoded_nodes,
            "raw_graph_object": record.graph_object,
        }
        _write_json_file(output_path, graph_payload)

        exported_graph_index.append(
            {
                "graph_id_int": record.graph_id_int,
                "graph_name": record.graph_name,
                "node_count": len(decoded_nodes),
                "source_pyugc_path": record.source_pyugc_path,
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    for record in node_def_records:
        file_stem = _sanitize_filename(f"node_def_{record.node_def_id_int}_{record.node_name}", max_length=120)
        output_path = pyugc_node_defs_directory / f"{file_stem}.json"
        payload = {
            "node_def_id_int": record.node_def_id_int,
            "node_def_index": int(record.node_def_id_int - 1610612736),
            "node_name": record.node_name,
            "source_pyugc_path": record.source_pyugc_path,
            "raw_node_def_object": record.node_def_object,
        }
        _write_json_file(output_path, payload)
        exported_node_def_index.append(
            {
                "node_def_id_int": record.node_def_id_int,
                "node_def_index": int(record.node_def_id_int - 1610612736),
                "node_name": record.node_name,
                "source_pyugc_path": record.source_pyugc_path,
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    graphs_index_path = node_graph_raw_root / "pyugc_graphs_index.json"
    node_defs_index_path = node_graph_raw_root / "pyugc_node_defs_index.json"
    _write_json_file(graphs_index_path, exported_graph_index)
    _write_json_file(node_defs_index_path, exported_node_def_index)

    return {
        "pyugc_graphs_count": len(exported_graph_index),
        "pyugc_graphs_index": str(graphs_index_path.relative_to(output_package_root)).replace("\\", "/"),
        "pyugc_node_defs_count": len(exported_node_def_index),
        "pyugc_node_defs_index": str(node_defs_index_path.relative_to(output_package_root)).replace("\\", "/"),
    }


