from __future__ import annotations

"""
report_node_graph_writeback_coverage.py

目标：
- 从“模板 .gil 的某张节点图”（通常是校准/全节点覆盖图）中，统计写回所需的样本覆盖情况；
- 输出一份 JSON 报告，告诉你：
  - 哪些 node type_id 有节点样本（可用于克隆生成节点）；
  - 哪些 dst 节点的 data 输入槽位(slot_index) 存在 data-link record 样本（可用于写回 data 连线）；
  - 哪些 src 节点类型在样本中出现过哪些 src_port_index（用于判断输出端口索引覆盖程度）。

设计原则：
- 不使用 try/except；失败直接抛错，便于定位。
- “不做语义猜测”：仅做样本统计与缺口提示，不尝试自动补齐未知端口索引规则。
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    with tempfile.TemporaryDirectory(prefix="ugc_dump_") as temp_dir:
        raw_json_path = Path(temp_dir) / "dump.json"
        dump_gil_to_json(str(input_path), str(raw_json_path))
        raw_dump_object = json.loads(raw_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_dump_object, dict):
        raise ValueError("DLL dump-json 顶层不是 dict")
    return raw_dump_object


def _get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")
    return payload_root


def _first_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _iter_graph_groups(node_graph_section: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups_value = node_graph_section.get("1")
    if isinstance(groups_value, list):
        return [item for item in groups_value if isinstance(item, dict)]
    if isinstance(groups_value, dict):
        return [groups_value]
    return []


def _iter_graph_entries_for_group(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries_value = group.get("1")
    if isinstance(entries_value, list):
        return [item for item in entries_value if isinstance(item, dict)]
    if isinstance(entries_value, dict):
        return [entries_value]
    return []


def _get_graph_id_from_entry(graph_entry: Dict[str, Any]) -> Optional[int]:
    header = _first_dict(graph_entry.get("1"))
    if isinstance(header, dict) and isinstance(header.get("5"), int):
        return int(header.get("5"))
    return None


def _find_graph_entry(payload_root: Dict[str, Any], graph_id_int: int) -> Dict[str, Any]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        raise ValueError("payload 缺少节点图段 '10'")
    for group in _iter_graph_groups(section):
        for entry in _iter_graph_entries_for_group(group):
            gid = _get_graph_id_from_entry(entry)
            if isinstance(gid, int) and int(gid) == int(graph_id_int):
                return entry
    raise ValueError(f"未找到 graph_id={int(graph_id_int)} 的 GraphEntry")


def _decode_type_id_from_node(node_object: Dict[str, Any]) -> int:
    binary_text = node_object.get("2")
    if not isinstance(binary_text, str) or not binary_text.startswith("<binary_data>"):
        raise ValueError("node['2'] 不是 <binary_data> 字符串，无法提取 type_id")
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(binary_text))
    if not isinstance(decoded, dict):
        raise ValueError("node['2'] decode 结果不是 dict")
    field_5 = decoded.get("field_5")
    if not isinstance(field_5, dict) or not isinstance(field_5.get("int"), int):
        raise ValueError("node['2'] decode 缺少 field_5.int(type_id)")
    return int(field_5["int"])


def _extract_nested_int(decoded_record: Dict[str, Any], path: Sequence[str]) -> Optional[int]:
    cursor: Any = decoded_record
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if not isinstance(cursor, dict):
        return None
    number = cursor.get("int")
    if isinstance(number, int):
        return int(number)
    return None


def _extract_data_record_slot_index(decoded_record: Dict[str, Any]) -> int:
    slot = _extract_nested_int(decoded_record, ["field_1", "message", "field_2"])
    return int(slot) if isinstance(slot, int) else 0


def _extract_data_record_src_port_index(decoded_record: Dict[str, Any]) -> Optional[int]:
    a = _extract_nested_int(decoded_record, ["field_5", "message", "field_2", "message", "field_1"])
    if isinstance(a, int):
        return int(a)
    b = _extract_nested_int(decoded_record, ["field_5", "message", "field_3", "message", "field_1"])
    if isinstance(b, int):
        return int(b)
    return None


def _is_link_record(*, record_bytes: bytes, node_id_set: set[int]) -> Tuple[bool, str]:
    decoded = decode_bytes_to_python(record_bytes)
    if not isinstance(decoded, dict):
        return False, ""
    other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
    if not isinstance(other_node_id, int):
        return False, ""
    if int(other_node_id) not in node_id_set:
        return False, ""
    is_data = "field_4" in decoded
    return True, ("data" if is_data else "flow")


def report_coverage(
    *,
    template_gil_path: Path,
    template_graph_id_int: int,
    mapping_path: Path,
    graph_generater_root: Path,
) -> Dict[str, Any]:
    raw_dump_object = _dump_gil_to_raw_json_object(Path(template_gil_path))
    payload_root = _get_payload_root(raw_dump_object)

    template_entry = _find_graph_entry(payload_root, int(template_graph_id_int))
    nodes_value = template_entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError("模板图缺少 nodes 列表 entry['3']")
    nodes = [n for n in nodes_value if isinstance(n, dict)]
    if not nodes:
        raise ValueError("模板图 nodes 为空")

    template_node_id_set: set[int] = set()
    node_type_by_node_id_int: Dict[int, int] = {}
    for node in nodes:
        node_id_value = node.get("1")
        if isinstance(node_id_value, list) and node_id_value and isinstance(node_id_value[0], int):
            node_id_int = int(node_id_value[0])
            template_node_id_set.add(node_id_int)
            node_type_by_node_id_int[node_id_int] = _decode_type_id_from_node(node)

    # type_id -> graph_generater_node_name
    mapping_object = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    if not isinstance(mapping_object, dict):
        raise TypeError("node_type_semantic_map.json must be dict")
    type_id_to_name: Dict[int, str] = {}
    for type_id_str, entry in mapping_object.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("scope") != "server":
            continue
        if not str(type_id_str).isdigit():
            continue
        type_id_to_name[int(type_id_str)] = str(entry.get("graph_generater_node_name") or "").strip()

    # NodeDef: name -> {inputs/outputs}
    graph_generater_root = Path(graph_generater_root).resolve()
    if not graph_generater_root.is_dir():
        raise FileNotFoundError(str(graph_generater_root))
    if str(graph_generater_root) not in sys.path:
        sys.path.insert(0, str(graph_generater_root))
    from engine.nodes.node_registry import get_node_registry
    from engine.utils.graph.graph_utils import is_flow_port_name

    registry = get_node_registry(graph_generater_root, include_composite=True)
    lib = registry.get_library()

    def find_unique_node_def_by_name(name_cn: str) -> Optional[Any]:
        if not name_cn:
            return None
        candidates = []
        for nd in lib.values():
            if str(getattr(nd, "name", "")) != name_cn:
                continue
            if hasattr(nd, "is_available_in_scope") and not nd.is_available_in_scope("server"):
                continue
            candidates.append(nd)
        if len(candidates) != 1:
            return None
        return candidates[0]

    # coverage accumulators
    type_ids_with_node_sample: set[int] = set()
    data_slot_templates_by_dst_type_id: Dict[int, Dict[int, Dict[str, Any]]] = {}
    flow_record_seen_by_type_id: set[int] = set()
    src_port_indices_by_src_type_id: Dict[int, set[int]] = {}

    for node in nodes:
        dst_type_id = _decode_type_id_from_node(node)
        type_ids_with_node_sample.add(int(dst_type_id))

        records = node.get("4")
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, str) or not record.startswith("<binary_data>"):
                continue
            record_bytes = parse_binary_data_hex_text(record)
            is_link, kind = _is_link_record(record_bytes=record_bytes, node_id_set=template_node_id_set)
            if not is_link:
                continue

            decoded = decode_bytes_to_python(record_bytes)
            if not isinstance(decoded, dict):
                raise ValueError("record decode 结果不是 dict")

            if kind == "flow":
                flow_record_seen_by_type_id.add(int(dst_type_id))
                continue

            # data link record（存在于 dst node 上）
            slot_index = _extract_data_record_slot_index(decoded)
            dst_port_index = _extract_nested_int(decoded, ["field_4"])
            src_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
            src_type_id = node_type_by_node_id_int.get(int(src_node_id)) if isinstance(src_node_id, int) else None
            src_port_index = _extract_data_record_src_port_index(decoded)

            bucket = data_slot_templates_by_dst_type_id.setdefault(int(dst_type_id), {})
            bucket.setdefault(
                int(slot_index),
                {
                    "slot_index": int(slot_index),
                    "dst_port_index": int(dst_port_index) if isinstance(dst_port_index, int) else None,
                    "example_src_type_id": int(src_type_id) if isinstance(src_type_id, int) else None,
                    "example_src_port_index": int(src_port_index) if isinstance(src_port_index, int) else None,
                },
            )

            if isinstance(src_type_id, int) and isinstance(src_port_index, int):
                src_port_indices_by_src_type_id.setdefault(int(src_type_id), set()).add(int(src_port_index))

    # build per-type report
    per_type: List[Dict[str, Any]] = []
    all_type_ids = sorted(type_ids_with_node_sample)
    for tid in all_type_ids:
        name = type_id_to_name.get(int(tid), "")
        nd = find_unique_node_def_by_name(name) if name else None
        expected_data_inputs: List[str] = []
        expected_data_outputs: List[str] = []
        if nd is not None:
            expected_data_inputs = [str(p) for p in (getattr(nd, "inputs", []) or []) if not is_flow_port_name(str(p))]
            expected_data_outputs = [str(p) for p in (getattr(nd, "outputs", []) or []) if not is_flow_port_name(str(p))]

        observed_slots = sorted((data_slot_templates_by_dst_type_id.get(int(tid)) or {}).keys())
        missing_slots = []
        if expected_data_inputs:
            missing_slots = [i for i in range(len(expected_data_inputs)) if i not in set(observed_slots)]

        observed_src_indices = sorted(list(src_port_indices_by_src_type_id.get(int(tid), set())))

        per_type.append(
            {
                "type_id": int(tid),
                "name": name,
                "has_node_sample": True,
                "has_flow_record_sample": int(tid) in flow_record_seen_by_type_id,
                "expected_data_inputs": expected_data_inputs,
                "expected_data_outputs": expected_data_outputs,
                "observed_data_input_slots": observed_slots,
                "missing_data_input_slots": [
                    {"slot_index": int(i), "port_name": expected_data_inputs[int(i)] if i < len(expected_data_inputs) else ""}
                    for i in missing_slots
                ],
                "data_slot_samples": [
                    (data_slot_templates_by_dst_type_id.get(int(tid)) or {}).get(int(i)) for i in observed_slots
                ],
                "observed_src_port_indices": observed_src_indices,
                "observed_src_port_index_count": len(observed_src_indices),
                "expected_data_output_count": len(expected_data_outputs),
            }
        )

    summary = {
        "template_gil": str(Path(template_gil_path).resolve()),
        "template_graph_id_int": int(template_graph_id_int),
        "node_count": len(nodes),
        "unique_type_id_count": len(type_ids_with_node_sample),
        "type_ids_with_any_data_slot_sample": len([k for k in data_slot_templates_by_dst_type_id.keys()]),
    }

    return {"summary": summary, "per_type": per_type}


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="从模板 .gil 的某张节点图统计“写回所需样本覆盖”，输出 JSON 报告（node sample / flow sample / data slot sample）。",
    )
    parser.add_argument("--template-gil", required=True, help="模板 .gil（用于提取节点/record 样本）")
    parser.add_argument("--template-graph-id", dest="template_graph_id_int", type=int, required=True, help="模板图 graph_id_int")
    parser.add_argument("--output-json", required=True, help="输出 JSON（强制写入 ugc_file_tools/out/）")
    parser.add_argument(
        "--node-type-map",
        dest="mapping_path",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名 映射文件（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=str(repo_root()),
        help="Graph_Generater 根目录（默认 workspace/Graph_Generater）",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = report_coverage(
        template_gil_path=Path(args.template_gil),
        template_graph_id_int=int(args.template_graph_id_int),
        mapping_path=Path(args.mapping_path),
        graph_generater_root=Path(args.graph_generater_root),
    )

    out_path = resolve_output_file_path_in_out_dir(Path(args.output_json))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 80)
    print("writeback coverage report generated:")
    print(f"- output_json: {str(out_path)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




