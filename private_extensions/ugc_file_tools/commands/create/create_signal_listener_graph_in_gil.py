from __future__ import annotations

"""
create_signal_listener_graph_in_gil.py

目标：
- 读取输入 `.gil` 中已存在的“信号定义”（payload_root['10']['5']['3']）
- 在同一份 `.gil` 的节点图段（payload_root['10']['1']）新增一张节点图：
  - 为每个信号生成一个【监听信号】节点实例
  - 节点会写入“信号名”常量 record（用于编辑器显示/绑定）

适用场景：
- 配合 `add_signal_definition_to_gil.py`：先从空存档批量写入信号，再用本脚本自动生成一张“信号墙”节点图，
  便于你在编辑器里直观看到每个信号与其节点定义是否可用。

实现策略（模板驱动，fail-closed）：
- 使用 dump-json（数值键结构）做 gil -> raw JSON
- 使用 template_gil 提供：
  - GraphEntry/header 的结构模板（graph_id scope/未知字段）
  - 监听信号节点的“信号名常量 record”结构模板
  - payload['10']['3']（复合节点库元信息）作为缺失时的自举来源
- 使用 `gil_dump_codec.protobuf_like.encode_message` 重编码 payload 并按原容器 header/footer 封装写回

注意：
- 本脚本只负责“把信号铺成监听节点”，不尝试自动连线/生成可运行逻辑。
- 不使用 try/except；失败直接抛错便于定位。
"""

import argparse
import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    with tempfile.TemporaryDirectory(prefix="ugc_dump_") as temp_dir:
        raw_json_path = Path(temp_dir) / "dump.json"
        dump_gil_to_json(str(input_path), str(raw_json_path))
        raw_dump_object = json.loads(raw_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw_dump_object, dict):
        raise ValueError("dump-json 顶层不是 dict")
    return raw_dump_object


def _get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    return payload_root


def _ensure_path_dict(root: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = root.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: Dict[str, Any] = {}
        root[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def _ensure_path_list(root: Dict[str, Any], key: str) -> List[Any]:
    value = root.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        root[key] = new_value
        return new_value
    raise ValueError(f"expected list at key={key!r}, got {type(value).__name__}")


def _first_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _first_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _set_int_node(node: Dict[str, Any], value: int) -> None:
    node["int"] = int(value)
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF


def _set_text_node_utf8(node: Dict[str, Any], text: str) -> None:
    raw_bytes = str(text).encode("utf-8")
    node["raw_hex"] = raw_bytes.hex()
    node["utf8"] = str(text)


def _decoded_field_map_to_dump_json_message(decoded_fields: Mapping[str, Any]) -> Dict[str, Any]:
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

    if isinstance(value, Mapping):
        if "message" in value:
            nested = value.get("message")
            if not isinstance(nested, Mapping):
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


def _decode_binary_data_text(binary_text: str) -> Dict[str, Any]:
    if not isinstance(binary_text, str) or not binary_text.startswith("<binary_data>"):
        raise ValueError("expected <binary_data> string")
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(binary_text))
    if not isinstance(decoded, dict):
        raise ValueError("decode result is not dict")
    return decoded


def _encode_node_property_binary_text(*, node_type_id_int: int) -> str:
    # 对齐样本：field_1=10001, field_2=20000, field_3=22001, field_5=type_id
    msg = {"1": 10001, "2": 20000, "3": 22001, "5": int(node_type_id_int)}
    return format_binary_data_hex_text(encode_message(msg))


def _find_template_graph_entry(template_payload_root: Dict[str, Any]) -> Dict[str, Any]:
    section = template_payload_root.get("10")
    if not isinstance(section, dict):
        raise ValueError("template_gil 缺少节点图段 payload['10']")
    groups = section.get("1")
    if isinstance(groups, dict):
        groups = [groups]
    if not isinstance(groups, list) or not groups:
        raise ValueError("template_gil 的 payload['10']['1'] 为空")
    wrapper = groups[0]
    if not isinstance(wrapper, dict):
        raise ValueError("template_gil graph wrapper 不是 dict")
    entries = wrapper.get("1")
    if isinstance(entries, dict):
        return entries
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        return entries[0]
    raise ValueError("template_gil wrapper['1'] 缺少 GraphEntry")


def _find_template_listener_node_and_constant_record(
    template_graph_entry: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    nodes = template_graph_entry.get("3")
    if not isinstance(nodes, list):
        raise ValueError("template GraphEntry 缺少 nodes 列表")
    for node in nodes:
        if not isinstance(node, dict):
            continue
        records = node.get("4")
        if not isinstance(records, list):
            continue
        for record_text in records:
            if not isinstance(record_text, str) or not record_text.startswith("<binary_data>"):
                continue
            decoded = decode_bytes_to_python(parse_binary_data_hex_text(record_text))
            if not isinstance(decoded, dict):
                continue
            field_3 = decoded.get("field_3")
            if not isinstance(field_3, dict):
                continue
            msg = field_3.get("message")
            if not isinstance(msg, dict):
                continue
            field_105 = msg.get("field_105")
            if not isinstance(field_105, dict):
                continue
            # 兼容两种形态：
            # 1) field_105 直接是 TextNode：{"raw_hex": "...", "utf8": "..."}
            # 2) field_105 是 wrapper message：{"message": {"field_1": TextNode}}
            if isinstance(field_105.get("raw_hex"), str):
                # 命中：该 record 是“信号名常量”
                return node, decoded
            nested = field_105.get("message")
            if isinstance(nested, dict):
                text_node = nested.get("field_1")
                if isinstance(text_node, dict) and isinstance(text_node.get("raw_hex"), str):
                    # 命中：该 record 是“信号名常量”
                    return node, decoded
    raise ValueError("template_gil 中未找到监听信号节点的“信号名常量 record”模板")


def _index_node_defs_by_id(section10: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    mapping: Dict[int, Dict[str, Any]] = {}
    node_defs_value = section10.get("2")
    if not isinstance(node_defs_value, list):
        return mapping
    for wrapper in node_defs_value:
        if not isinstance(wrapper, Mapping):
            continue
        node_def = wrapper.get("1")
        if not isinstance(node_def, dict):
            continue
        meta = node_def.get("4")
        meta_1 = meta.get("1") if isinstance(meta, Mapping) else None
        node_def_id = meta_1.get("5") if isinstance(meta_1, Mapping) else None
        if isinstance(node_def_id, int):
            mapping[int(node_def_id)] = node_def
    return mapping


def _extract_signal_name_port_index_from_listen_node_def(node_def: Mapping[str, Any]) -> int:
    ports = node_def.get("106")
    if not isinstance(ports, list):
        raise ValueError("listen node_def 缺少 106 端口列表")
    for port in ports:
        if not isinstance(port, Mapping):
            continue
        if str(port.get("1") or "").strip() == "信号名":
            port_index = port.get("8")
            if not isinstance(port_index, int):
                raise ValueError("listen node_def 的 信号名 端口缺少 8(index)")
            return int(port_index)
    raise ValueError("listen node_def 的 106 端口列表未找到 '信号名'")


def _collect_signal_entries(section10: Mapping[str, Any]) -> List[Dict[str, Any]]:
    section5 = section10.get("5")
    if not isinstance(section5, Mapping):
        return []
    entries = section5.get("3")
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]


def _choose_next_graph_id(*, existing_graph_ids: Sequence[int], scope_mask: int) -> int:
    candidates = [int(v) for v in existing_graph_ids if isinstance(v, int) and (int(v) & 0xFF800000) == int(scope_mask)]
    existing_set = set(int(v) for v in existing_graph_ids if isinstance(v, int))
    if not candidates:
        candidate = int(scope_mask) | 1
        while candidate in existing_set:
            candidate += 1
        return int(candidate)
    candidate = max(candidates) + 1
    while candidate in existing_set:
        candidate += 1
    return int(candidate)


def _collect_existing_graph_ids(section10: Mapping[str, Any]) -> List[int]:
    groups = section10.get("1")
    if isinstance(groups, dict):
        groups = [groups]
    if not isinstance(groups, list):
        return []
    ids: List[int] = []
    for wrapper in groups:
        if not isinstance(wrapper, Mapping):
            continue
        entries = wrapper.get("1")
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            header = _first_dict(entry.get("1"))
            graph_id = header.get("5") if isinstance(header, dict) else None
            if isinstance(graph_id, int):
                ids.append(int(graph_id))
    return ids


def _build_patched_signal_name_record(
    *,
    template_decoded_record: Dict[str, Any],
    signal_name: str,
    port_index_int: int,
) -> str:
    decoded = copy.deepcopy(template_decoded_record)
    field_7 = decoded.get("field_7")
    if not isinstance(field_7, dict):
        raise ValueError("template record missing field_7")
    _set_int_node(field_7, int(port_index_int))

    field_3 = decoded.get("field_3")
    if not isinstance(field_3, dict) or not isinstance(field_3.get("message"), dict):
        raise ValueError("template record missing field_3.message")
    msg = field_3.get("message")
    if not isinstance(msg, dict):
        raise ValueError("template record field_3.message is not dict")
    field_105 = msg.get("field_105")
    if not isinstance(field_105, dict):
        raise ValueError("template record missing field_3.message.field_105")
    # 兼容两种形态：
    # 1) field_105 直接是 TextNode：{"raw_hex": "...", "utf8": "..."}
    # 2) field_105 是 wrapper message：{"message": {"field_1": TextNode}}
    if isinstance(field_105.get("raw_hex"), str):
        _set_text_node_utf8(field_105, str(signal_name))
    else:
        nested = field_105.get("message")
        if not isinstance(nested, dict) or not isinstance(nested.get("field_1"), dict):
            raise ValueError("template record field_3.message.field_105 结构不支持（期望 TextNode 或 wrapper message.field_1）")
        _set_text_node_utf8(nested["field_1"], str(signal_name))

    dump_json_message = _decoded_field_map_to_dump_json_message(decoded)
    record_bytes = encode_message(dump_json_message)
    return format_binary_data_hex_text(record_bytes)


def create_signal_listener_graph_in_gil(
    *,
    input_gil_path: Path,
    template_gil_path: Path,
    output_gil_path: Path,
    new_graph_name: str,
    new_graph_id_int: Optional[int],
) -> Dict[str, Any]:
    template_raw = _dump_gil_to_raw_json_object(Path(template_gil_path))
    template_payload_root = _get_payload_root(template_raw)
    template_section10 = template_payload_root.get("10")
    if not isinstance(template_section10, dict):
        raise ValueError("template_gil 缺少 payload['10']")

    template_graph_entry = _find_template_graph_entry(template_payload_root)
    template_header = _first_dict(template_graph_entry.get("1"))
    if not isinstance(template_header, dict):
        raise ValueError("template GraphEntry 缺少 header(entry['1'][0])")

    template_listener_node, template_signal_record_decoded = _find_template_listener_node_and_constant_record(template_graph_entry)

    raw_dump_object = _dump_gil_to_raw_json_object(Path(input_gil_path))
    payload_root = _get_payload_root(raw_dump_object)
    section10 = _ensure_path_dict(payload_root, "10")

    # 自举缺失的复合节点库元信息（payload['10']['3']）
    if "3" not in section10:
        section10["3"] = copy.deepcopy(template_section10.get("3"))

    node_defs_by_id = _index_node_defs_by_id(section10)
    signal_entries = _collect_signal_entries(section10)
    if not signal_entries:
        raise ValueError("输入存档未找到任何信号定义（payload['10']['5']['3'] 为空）")

    # 生成 nodes：每个信号一个监听节点
    nodes: List[Dict[str, Any]] = []
    next_node_id_int = 1
    # 简易布局：每行 5 个
    start_x = -500.0
    start_y = -250.0
    step_x = 320.0
    step_y = 220.0

    for idx, entry in enumerate(signal_entries):
        signal_name = str(entry.get("3") or "").strip()
        if signal_name == "":
            continue
        signal_index = entry.get("6")
        if not isinstance(signal_index, int):
            continue

        listen_meta = entry.get("2")
        if not isinstance(listen_meta, Mapping):
            continue
        listen_node_def_id = listen_meta.get("5")
        if not isinstance(listen_node_def_id, int):
            continue

        listen_node_def = node_defs_by_id.get(int(listen_node_def_id))
        if not isinstance(listen_node_def, Mapping):
            raise ValueError(f"未找到监听信号 node_def：id={int(listen_node_def_id)} name={signal_name!r}")
        signal_name_port_index = _extract_signal_name_port_index_from_listen_node_def(listen_node_def)

        node_obj = copy.deepcopy(template_listener_node)
        node_obj["1"] = [int(next_node_id_int)]
        next_node_id_int += 1

        node_prop_text = _encode_node_property_binary_text(node_type_id_int=int(listen_node_def_id))
        node_obj["2"] = str(node_prop_text)
        node_obj["3"] = str(node_prop_text)
        node_obj["9"] = int(signal_index)

        row = int(idx // 5)
        col = int(idx % 5)
        node_obj["5"] = float(start_x + float(col) * step_x)
        node_obj["6"] = float(start_y + float(row) * step_y)

        node_obj["4"] = [
            _build_patched_signal_name_record(
                template_decoded_record=template_signal_record_decoded,
                signal_name=signal_name,
                port_index_int=int(signal_name_port_index),
            )
        ]

        nodes.append(node_obj)

    if not nodes:
        raise ValueError("未生成任何监听信号节点（信号列表可能为空或缺字段）")

    # 新 GraphEntry
    existing_graph_ids = _collect_existing_graph_ids(section10)
    scope_mask = int(int(template_header.get("5") or 0) & 0xFF800000)
    allocated_graph_id = (
        int(new_graph_id_int)
        if new_graph_id_int is not None
        else _choose_next_graph_id(existing_graph_ids=existing_graph_ids, scope_mask=scope_mask)
    )
    if allocated_graph_id in set(existing_graph_ids):
        raise ValueError(f"new_graph_id 已存在：{allocated_graph_id}")

    new_entry = {
        "1": [copy.deepcopy(template_header)],
        "2": [str(new_graph_name).strip()],
        "3": nodes,
    }
    new_entry["1"][0]["5"] = int(allocated_graph_id)

    # 按“一图一个 wrapper”追加到 payload['10']['1']
    groups_list = _ensure_path_list(section10, "1")
    # 注意：部分存档中 section10['7'] 并不等于 groups 数（例如为 1），强行改写可能导致游戏侧静默拒绝导入。
    # 这里仅在其“看起来就是计数字段”（与追加前 group 数一致）时才同步更新。
    old_group_count = int(len([g for g in groups_list if isinstance(g, dict)]))
    old_field_7 = section10.get("7")
    groups_list.append({"1": [new_entry]})
    new_group_count = int(len([g for g in groups_list if isinstance(g, dict)]))
    if isinstance(old_field_7, int) and int(old_field_7) == int(old_group_count):
        section10["7"] = int(new_group_count)

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(Path(input_gil_path))
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(Path(input_gil_path).resolve()),
        "template_gil": str(Path(template_gil_path).resolve()),
        "output_gil": str(output_path),
        "graph_id_int": int(allocated_graph_id),
        "graph_name": str(new_graph_name).strip(),
        "signal_count": len(signal_entries),
        "listener_nodes_written": len(nodes),
        "groups_count": int(section10.get("7") if isinstance(section10.get("7"), int) else 0),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="为存档内的所有信号生成一个“监听信号节点墙”节点图，并写回输出新 .gil。")
    parser.add_argument("--input-gil", required=True, help="输入 .gil（必须已包含信号定义：payload['10']['5']['3']）")
    parser.add_argument("--template-gil", required=True, help="模板 .gil（用于提供 GraphEntry/record/section10['3'] 模板）")
    parser.add_argument("--output-gil", required=True, help="输出 .gil（强制写入 ugc_file_tools/out/；不要覆盖重要样本）")
    parser.add_argument("--new-graph-name", required=True, help="新节点图名称（显示名）")
    parser.add_argument("--new-graph-id", dest="new_graph_id_int", type=int, default=None, help="可选：指定新 graph_id")

    args = parser.parse_args(list(argv) if argv is not None else None)
    result = create_signal_listener_graph_in_gil(
        input_gil_path=Path(args.input_gil),
        template_gil_path=Path(args.template_gil),
        output_gil_path=Path(args.output_gil),
        new_graph_name=str(args.new_graph_name),
        new_graph_id_int=(int(args.new_graph_id_int) if args.new_graph_id_int is not None else None),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()




