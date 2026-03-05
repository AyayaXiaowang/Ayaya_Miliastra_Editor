from __future__ import annotations

"""
create_type_id_matrix_in_gil.py

目标：
- 在一个现有 `.gil` 文件中新增一张“type_id 矩阵图”（GraphEntry），用于人工校准：
  - 图中节点按从左到右、从上到下排列；
  - 每个节点强制写入一个指定的 node_type_id_int（即节点 type_id）；
  - 默认不连线、默认清空 records，尽量避免携带旧引用。

用途：
- 当我们暂时不知道某些 type_id 对应的节点中文名时，可以把 type_id 批量塞进图里，
  由你在官方编辑器/游戏内查看节点显示名后截图反馈，从而反向补全 type_id→节点名映射。

实现策略：
- 使用 dump-json（数值键结构）做 gil -> raw JSON
- 在 dump-json 的 payload(root['4']) 内定位节点图段 `10`
- 从现有 GraphEntry 中选择一个“模板节点”（优先 record 最少）作为结构原型
- 对模板节点的 data_2/data_3 二进制块解码，修改 field_5.int 为目标 type_id，再重编码回 <binary_data>
- 克隆生成 N 个节点并按网格排布，写入新 GraphEntry，追加到新的 group（保持“一图一个 group”）
- 使用 `gil_dump_codec.encode_message` 重编码 payload 并按原容器 header/footer 封装写回

注意：
- 本脚本不会保证所有 type_id 都是有效节点；无效 ID 可能在编辑器中显示为未知/报错。
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    with tempfile.TemporaryDirectory(prefix="ugc_typeid_dump_") as temp_dir:
        raw_json_path = Path(temp_dir) / "dump.json"
        dump_gil_to_json(str(input_path), str(raw_json_path))
        raw_dump_object = json.loads(raw_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_dump_object, dict):
        raise ValueError("dump-json 顶层不是 dict")
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


def _ensure_list(root: Dict[str, Any], key: str) -> List[Any]:
    value = root.get(key)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        root[key] = [value]
        return root[key]
    if value is None:
        root[key] = []
        return root[key]
    raise ValueError(f"expected list/dict/None at {key!r}, got {type(value).__name__}")


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


def _collect_existing_graph_ids(payload_root: Dict[str, Any]) -> List[int]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return []
    ids: List[int] = []
    for group in _iter_graph_groups(section):
        for entry in _iter_graph_entries_for_group(group):
            gid = _get_graph_id_from_entry(entry)
            if isinstance(gid, int):
                ids.append(int(gid))
    return ids


def _choose_next_graph_id(*, existing_graph_ids: Sequence[int], scope_mask: int) -> int:
    existing_set = set(int(v) for v in existing_graph_ids if isinstance(v, int))
    candidates = [int(v) for v in existing_graph_ids if isinstance(v, int) and (int(v) & 0xFF800000) == int(scope_mask)]
    if not candidates:
        candidate = int(scope_mask) | 1
        while candidate in existing_set:
            candidate += 1
        return int(candidate)
    candidate = max(candidates) + 1
    while candidate in existing_set:
        candidate += 1
    return int(candidate)


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


def _decoded_field_map_to_dump_json_message(decoded_fields: Dict[str, Any]) -> Dict[str, Any]:
    message: Dict[str, Any] = {}
    for key, value in decoded_fields.items():
        if not isinstance(key, str) or not key.startswith("field_"):
            continue
        suffix = key.replace("field_", "")
        if not suffix.isdigit():
            continue
        message[str(int(suffix))] = _decoded_value_to_dump_json_value(value)
    return message


def _decoded_value_to_dump_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decoded_value_to_dump_json_value(item) for item in value]

    if isinstance(value, dict):
        if "message" in value:
            nested = value.get("message")
            if not isinstance(nested, dict):
                raise ValueError("decoded message is not dict")
            return _decoded_field_map_to_dump_json_message(nested)

        if "int" in value:
            raw_int = value.get("int")
            if not isinstance(raw_int, int):
                raise ValueError("decoded int node missing int")
            return int(raw_int)

        if "fixed32_float" in value:
            float_value = value.get("fixed32_float")
            if not isinstance(float_value, float):
                raise ValueError("decoded fixed32_float node missing fixed32_float")
            return float(float_value)

        if "fixed64_double" in value:
            double_value = value.get("fixed64_double")
            if not isinstance(double_value, float):
                raise ValueError("decoded fixed64_double node missing fixed64_double")
            return float(double_value)

        if "raw_hex" in value:
            raw_hex = value.get("raw_hex")
            if not isinstance(raw_hex, str):
                raise ValueError("decoded raw_hex node missing raw_hex")
            raw_bytes = bytes.fromhex(raw_hex)
            return format_binary_data_hex_text(raw_bytes)

        raise ValueError(f"unsupported decoded node: keys={sorted(value.keys())}")

    raise ValueError(f"unsupported decoded value type: {type(value).__name__}")


def _ensure_int_node(decoded_fields: Dict[str, Any], key: str, value: int) -> None:
    node = decoded_fields.get(key)
    if not isinstance(node, dict):
        raise ValueError(f"expected decoded int node at {key!r}, got {type(node).__name__}")
    node["int"] = int(value)
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF


def _patch_node_type_id_in_binary_text(binary_text: str, new_type_id_int: int) -> str:
    if not isinstance(binary_text, str) or not binary_text.startswith("<binary_data>"):
        raise ValueError("binary_text 不是 <binary_data> 字符串")
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(binary_text))
    if not isinstance(decoded, dict):
        raise ValueError("binary_text decode 结果不是 dict")
    field_5 = decoded.get("field_5")
    if not isinstance(field_5, dict):
        raise ValueError("binary_text decode 缺少 field_5")
    _ensure_int_node(decoded, "field_5", int(new_type_id_int))
    dump_json_message = _decoded_field_map_to_dump_json_message(decoded)
    out_bytes = encode_message(dump_json_message)
    return format_binary_data_hex_text(out_bytes)


def _choose_template_node_for_matrix(template_entry: Dict[str, Any]) -> Dict[str, Any]:
    nodes_value = template_entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError("模板图缺少 nodes 列表 entry['3']")
    nodes = [n for n in nodes_value if isinstance(n, dict)]
    if not nodes:
        raise ValueError("模板图 nodes 为空")

    def record_len(n: Dict[str, Any]) -> int:
        recs = n.get("4")
        return len(recs) if isinstance(recs, list) else 0

    nodes_sorted = sorted(nodes, key=lambda n: (record_len(n), int(n.get("1")[0]) if isinstance(n.get("1"), list) and n.get("1") else 0))
    return nodes_sorted[0]




# === Public facade (stable, cross-module) ===
#
# NOTE:
# - External modules must not import underscored private helpers from this module.
# - Keep these wrappers stable; internal implementations may evolve freely.


def dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    return _dump_gil_to_raw_json_object(input_gil_file_path)


def get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    return _get_payload_root(raw_dump_object)


def first_dict(value: Any) -> Optional[Dict[str, Any]]:
    return _first_dict(value)


def ensure_list(root: Dict[str, Any], key: str) -> List[Any]:
    return _ensure_list(root, key)


def iter_graph_groups(node_graph_section: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _iter_graph_groups(node_graph_section)


def iter_graph_entries_for_group(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _iter_graph_entries_for_group(group)


def collect_existing_graph_ids(payload_root: Dict[str, Any]) -> List[int]:
    return _collect_existing_graph_ids(payload_root)


def choose_next_graph_id(*, existing_graph_ids: Sequence[int], scope_mask: int) -> int:
    return _choose_next_graph_id(existing_graph_ids=existing_graph_ids, scope_mask=scope_mask)


def find_graph_entry(payload_root: Dict[str, Any], graph_id_int: int) -> Dict[str, Any]:
    return _find_graph_entry(payload_root, graph_id_int)


def patch_node_type_id_in_binary_text(binary_text: str, new_type_id_int: int) -> str:
    return _patch_node_type_id_in_binary_text(binary_text, new_type_id_int)


def choose_template_node_for_matrix(template_entry: Dict[str, Any]) -> Dict[str, Any]:
    return _choose_template_node_for_matrix(template_entry)


def create_type_id_matrix_graph(
    *,
    input_gil_path: Path,
    output_gil_path: Path,
    template_graph_id_int: int,
    new_graph_name: str,
    start_type_id_int: int,
    count: int,
    columns: int,
    spacing_x: float,
    spacing_y: float,
    origin_x: Optional[float],
    origin_y: Optional[float],
) -> Dict[str, Any]:
    raw_dump_object = _dump_gil_to_raw_json_object(Path(input_gil_path))
    payload_root = _get_payload_root(raw_dump_object)

    section = payload_root.get("10")
    if not isinstance(section, dict):
        raise ValueError("输入 .gil 缺少节点图段 payload['10']")

    groups_list = _ensure_list(section, "1")
    group_dicts = [g for g in groups_list if isinstance(g, dict)]
    if not group_dicts:
        raise ValueError("payload['10']['1'] 为空，无法追加新图")

    template_entry = _find_graph_entry(payload_root, int(template_graph_id_int))
    template_group = group_dicts[0]

    template_node = _choose_template_node_for_matrix(template_entry)
    if not isinstance(template_node, dict):
        raise ValueError("无法选择模板节点")

    base_x = float(template_node.get("5", 0.0) or 0.0)
    base_y = float(template_node.get("6", 0.0) or 0.0)
    origin_x_value = float(origin_x) if origin_x is not None else base_x
    origin_y_value = float(origin_y) if origin_y is not None else base_y

    start_tid = int(start_type_id_int)
    total = int(count)
    if total <= 0:
        raise ValueError("count 必须 > 0")
    cols = int(columns)
    if cols <= 0:
        raise ValueError("columns 必须 > 0")

    # 新图 graph_id
    existing_graph_ids = _collect_existing_graph_ids(payload_root)
    scope_mask = int(template_graph_id_int) & 0xFF800000
    new_graph_id_int = _choose_next_graph_id(existing_graph_ids=existing_graph_ids, scope_mask=scope_mask)

    # 克隆模板 entry 并替换 nodes
    new_entry = copy.deepcopy(template_entry)
    header = _first_dict(new_entry.get("1"))
    if not isinstance(header, dict):
        raise ValueError("模板 entry 缺少 header")
    header["5"] = int(new_graph_id_int)
    name_text = str(new_graph_name or "").strip()
    if name_text == "":
        name_text = f"type_id_matrix_{start_tid}_{start_tid + total - 1}"
    new_entry["2"] = [name_text]

    new_nodes: List[Dict[str, Any]] = []
    for i in range(total):
        type_id_int = int(start_tid + i)
        node_id_int = int(i + 1)
        col = int(i % cols)
        row = int(i // cols)
        x = float(origin_x_value + float(col) * float(spacing_x))
        y = float(origin_y_value + float(row) * float(spacing_y))

        node_obj = copy.deepcopy(template_node)
        node_obj["1"] = [node_id_int]
        node_obj["5"] = float(x)
        node_obj["6"] = float(y)
        node_obj["4"] = []

        # 强制写入 type_id：同时改 data_2 与 data_3
        node_obj["2"] = _patch_node_type_id_in_binary_text(str(node_obj.get("2")), type_id_int)
        node_obj["3"] = _patch_node_type_id_in_binary_text(str(node_obj.get("3")), type_id_int)

        new_nodes.append(node_obj)

    new_entry["3"] = new_nodes

    # 一图一个 group：克隆模板 group 元数据，但 graphs 列表替换为 [new_entry]
    new_group: Dict[str, Any] = {}
    for key, value in template_group.items():
        if key == "1":
            continue
        new_group[str(key)] = copy.deepcopy(value)
    new_group["1"] = [new_entry]
    groups_list.append(new_group)

    # 同步 section['7']（经验：group 数）
    section["7"] = int(len([item for item in groups_list if isinstance(item, dict)]))

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(Path(input_gil_path))
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)

    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(Path(input_gil_path).resolve()),
        "output_gil": str(output_path),
        "template_graph_id_int": int(template_graph_id_int),
        "new_graph_id_int": int(new_graph_id_int),
        "new_graph_name": name_text,
        "start_type_id_int": int(start_tid),
        "end_type_id_int": int(start_tid + total - 1),
        "nodes_written": int(total),
        "columns": int(cols),
        "spacing_x": float(spacing_x),
        "spacing_y": float(spacing_y),
        "origin_x": float(origin_x_value),
        "origin_y": float(origin_y_value),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="在 .gil 内新增一张 type_id 矩阵图（用于人工校准 type_id→节点名）。")
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径（建议先备份）")
    parser.add_argument("output_gil_file", help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）")
    parser.add_argument("--template-graph-id", dest="template_graph_id_int", type=int, required=True, help="用于克隆结构的模板 graph_id_int")
    parser.add_argument("--new-graph-name", dest="new_graph_name", default="", help="新图名称（默认自动生成）")
    parser.add_argument("--start-type-id", dest="start_type_id_int", type=int, required=True, help="起始 type_id（包含）")
    parser.add_argument("--count", dest="count", type=int, default=200, help="节点数量（默认 200）")
    parser.add_argument("--columns", dest="columns", type=int, default=20, help="每行列数（默认 20）")
    parser.add_argument("--spacing-x", dest="spacing_x", type=float, default=520.0, help="横向间距（默认 520）")
    parser.add_argument("--spacing-y", dest="spacing_y", type=float, default=340.0, help="纵向间距（默认 340）")
    parser.add_argument("--origin-x", dest="origin_x", type=float, default=None, help="起始 x 坐标（默认取模板节点 x）")
    parser.add_argument("--origin-y", dest="origin_y", type=float, default=None, help="起始 y 坐标（默认取模板节点 y）")

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = create_type_id_matrix_graph(
        input_gil_path=Path(args.input_gil_file),
        output_gil_path=resolve_output_file_path_in_out_dir(Path(args.output_gil_file)),
        template_graph_id_int=int(args.template_graph_id_int),
        new_graph_name=str(args.new_graph_name),
        start_type_id_int=int(args.start_type_id_int),
        count=int(args.count),
        columns=int(args.columns),
        spacing_x=float(args.spacing_x),
        spacing_y=float(args.spacing_y),
        origin_x=(float(args.origin_x) if args.origin_x is not None else None),
        origin_y=(float(args.origin_y) if args.origin_y is not None else None),
    )

    print("=" * 80)
    print("type_id 矩阵图已生成：")
    for key in sorted(report.keys()):
        print(f"- {key}: {report.get(key)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




