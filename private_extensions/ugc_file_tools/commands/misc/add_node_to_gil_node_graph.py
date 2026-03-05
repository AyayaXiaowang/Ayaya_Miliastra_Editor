from __future__ import annotations

"""
add_node_to_gil_node_graph.py

目标：
- 在不实现“完整节点图语义写回”的前提下，先提供一个最小可用闭环：
  - 使用 dump-json（数值键结构）进行 gil -> raw JSON
  - 定位 payload(root['4']) 内的节点图段（field '10'）
  - 在指定 graph_id 的 GraphEntry 内新增一个节点（默认克隆一个现有节点作为模板）
  - 重新编码 payload 并按原容器 header/footer 封装写回输出新的 .gil

设计原则：
- 未识别字段一律原样保留（我们只在 nodes 列表末尾追加一个 node dict）。
- 默认尽量避免复制“连线 record”（record 内若出现 field_5.message.field_1 指向其它 node_id，则视为连线/引用，克隆时默认剔除）。
- 不使用 try/except；失败应直接抛错，便于定位。
"""

import argparse
import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.console_encoding import configure_console_encoding


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    with tempfile.TemporaryDirectory(prefix="ugc_nodegraph_dump_") as temp_dir:
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


def _iter_graph_entries(payload_root: Dict[str, Any]) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    迭代所有 GraphEntry，返回 (graph_entry, header)。

    当前样本形态（简化）：
    - payload['10'] = nodegraph_section
    - nodegraph_section['1'] = [ wrapper, wrapper, ... ]
    - wrapper['1'] = [ graph_entry, ... ]
    - graph_entry['1'] = [ header, ... ]
    - header['5'] = graph_id
    """
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return

    wrapper_list = section.get("1")
    wrappers: List[Dict[str, Any]] = []
    if isinstance(wrapper_list, list):
        wrappers = [item for item in wrapper_list if isinstance(item, dict)]
    elif isinstance(wrapper_list, dict):
        wrappers = [wrapper_list]
    else:
        return

    for wrapper in wrappers:
        graph_list = wrapper.get("1")
        graph_entries: List[Dict[str, Any]] = []
        if isinstance(graph_list, list):
            graph_entries = [item for item in graph_list if isinstance(item, dict)]
        elif isinstance(graph_list, dict):
            graph_entries = [graph_list]

        for graph_entry in graph_entries:
            headers_value = graph_entry.get("1")
            header = None
            if isinstance(headers_value, list) and headers_value and isinstance(headers_value[0], dict):
                header = headers_value[0]
            elif isinstance(headers_value, dict):
                header = headers_value
            if not isinstance(header, dict):
                continue
            yield graph_entry, header


def _find_graph_entry(payload_root: Dict[str, Any], graph_id_int: int) -> Dict[str, Any]:
    target = int(graph_id_int)
    for graph_entry, header in _iter_graph_entries(payload_root):
        graph_id_value = header.get("5")
        if isinstance(graph_id_value, int) and int(graph_id_value) == target:
            return graph_entry
    raise ValueError(f"未找到节点图 graph_id={target}（payload['10'] 内）。")


def _first_int(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _collect_node_ids(nodes: Sequence[Any]) -> set[int]:
    node_ids: set[int] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = _first_int(node.get("1"))
        if isinstance(node_id, int):
            node_ids.add(int(node_id))
    return node_ids


def _choose_next_node_id(existing_ids: Sequence[int]) -> int:
    cleaned = [int(v) for v in existing_ids if isinstance(v, int)]
    if not cleaned:
        return 1
    return max(cleaned) + 1


def _extract_nested_int(decoded_record: Dict[str, Any], path: List[str]) -> Optional[int]:
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


def _ensure_int_node(decoded_fields: Dict[str, Any], key: str, value: int) -> None:
    node = decoded_fields.get(key)
    if not isinstance(node, dict):
        raise ValueError(f"expected decoded int node at {key!r}, got {type(node).__name__}")
    node["int"] = int(value)
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF


def _decoded_field_map_to_dump_json_message(decoded_fields: Mapping[str, Any]) -> Dict[str, Any]:
    """
    将 decode_gil.decode_bytes_to_python(...) 返回的 field_*/message 结构
    转回 encode_message 可接受的 “dump-json 数值键结构”。

    说明：
    - 该转换逻辑最早用于结构体 blob 写回，这里复用到“节点图 record 写回”。
    """
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


def _is_probable_link_record(*, record_bytes: bytes, node_id_set: set[int]) -> bool:
    """
    判定 record 是否为“连线/引用 record”。

    经验规则：
    - 若 decode 后存在 field_5.message.field_1.int 且命中当前图的 node_id_set，
      则视为连线/引用（flow/data edge 等），克隆节点时默认应剔除。
    """
    decoded = decode_bytes_to_python(record_bytes)
    if not isinstance(decoded, dict):
        return False
    other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
    if not isinstance(other_node_id, int):
        return False
    return int(other_node_id) in node_id_set


def _iter_record_binary_strings(node: Dict[str, Any]) -> List[str]:
    value = node.get("4")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str):
        return [value]
    return []


def _strip_link_records_from_node(*, node: Dict[str, Any], node_id_set: set[int]) -> None:
    records_value = node.get("4")
    if not isinstance(records_value, list):
        return

    kept: List[Any] = []
    for record in records_value:
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            kept.append(record)
            continue
        record_bytes = parse_binary_data_hex_text(record)
        if _is_probable_link_record(record_bytes=record_bytes, node_id_set=node_id_set):
            continue
        kept.append(record)
    node["4"] = kept


def _find_node_by_id(nodes_value: List[Any], node_id_int: int) -> Dict[str, Any]:
    target = int(node_id_int)
    for node in nodes_value:
        if not isinstance(node, dict):
            continue
        node_id_value = _first_int(node.get("1"))
        if isinstance(node_id_value, int) and int(node_id_value) == target:
            return node
    raise ValueError(f"未找到 node_id={target}")


def _ensure_record_list(node: Dict[str, Any]) -> List[Any]:
    records = node.get("4")
    if isinstance(records, list):
        return records
    if records is None:
        node["4"] = []
        return node["4"]
    raise ValueError(f"node['4'] 期望为 list 或缺失，但收到: {type(records).__name__}")


def _find_flow_link_record_text(
    *,
    node: Dict[str, Any],
    template_dst_node_id_int: int,
) -> str:
    """
    在 node 的 records 中定位一条“flow 连线 record”（record 不包含 field_4），并且其 field_5.message.field_1 指向 template_dst_node_id。
    """
    records = _ensure_record_list(node)
    target_dst = int(template_dst_node_id_int)
    for record in records:
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        record_bytes = parse_binary_data_hex_text(record)
        decoded = decode_bytes_to_python(record_bytes)
        if not isinstance(decoded, dict):
            continue
        if "field_4" in decoded:
            # data edge/其它携带 field_4 的 record，不视为 flow link
            continue
        other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
        if isinstance(other_node_id, int) and int(other_node_id) == target_dst:
            return record
    raise ValueError(f"未在源节点 records 中找到指向 dst={target_dst} 的 flow 连线 record 模板。")


def add_flow_link_by_cloning_template_record(
    *,
    graph_entry: Dict[str, Any],
    src_node_id_int: int,
    template_dst_node_id_int: int,
    new_dst_node_id_int: int,
) -> Dict[str, Any]:
    """
    通过“克隆现有 flow record”的方式新增一条 flow 连线：
    - record 存放在 src 节点上
    - record 内 field_5.message.field_1 指向 dst 节点 id
    """
    nodes_value = graph_entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError("graph_entry['3'] 期望为 nodes list")

    src_node = _find_node_by_id(nodes_value, int(src_node_id_int))
    _find_node_by_id(nodes_value, int(template_dst_node_id_int))
    _find_node_by_id(nodes_value, int(new_dst_node_id_int))

    template_record_text = _find_flow_link_record_text(
        node=src_node,
        template_dst_node_id_int=int(template_dst_node_id_int),
    )
    template_record_bytes = parse_binary_data_hex_text(template_record_text)
    decoded_template = decode_bytes_to_python(template_record_bytes)
    if not isinstance(decoded_template, dict):
        raise ValueError("flow record 模板 decode 结果不是 dict")

    decoded_new = copy.deepcopy(decoded_template)
    field_5 = decoded_new.get("field_5")
    if not isinstance(field_5, dict) or not isinstance(field_5.get("message"), dict):
        raise ValueError("flow record 缺少 field_5.message")
    field_5_message = field_5.get("message")
    if not isinstance(field_5_message, dict):
        raise ValueError("flow record field_5.message 不是 dict")
    if "field_1" not in field_5_message:
        raise ValueError("flow record field_5.message 缺少 field_1(dst_node_id)")
    _ensure_int_node(field_5_message, "field_1", int(new_dst_node_id_int))

    dump_json_message = _decoded_field_map_to_dump_json_message(decoded_new)
    record_bytes = encode_message(dump_json_message)
    record_text = format_binary_data_hex_text(record_bytes)

    src_records = _ensure_record_list(src_node)
    src_records.append(record_text)

    return {
        "kind": "flow",
        "src_node_id_int": int(src_node_id_int),
        "template_dst_node_id_int": int(template_dst_node_id_int),
        "new_dst_node_id_int": int(new_dst_node_id_int),
        "src_record_count_after": len(src_records),
    }


def _choose_template_node(
    *,
    nodes: List[Dict[str, Any]],
    node_id_set: set[int],
    template_node_id: Optional[int],
    strip_link_records: bool,
) -> Dict[str, Any]:
    if template_node_id is not None:
        target = int(template_node_id)
        for node in nodes:
            node_id = _first_int(node.get("1"))
            if isinstance(node_id, int) and int(node_id) == target:
                return node
        raise ValueError(f"未找到 template_node_id={target}")

    if strip_link_records:
        for node in nodes:
            record_texts = _iter_record_binary_strings(node)
            has_link = False
            for record in record_texts:
                if not record.startswith("<binary_data>"):
                    continue
                record_bytes = parse_binary_data_hex_text(record)
                if _is_probable_link_record(record_bytes=record_bytes, node_id_set=node_id_set):
                    has_link = True
                    break
            if not has_link:
                return node

    return nodes[-1]


def add_node_to_graph_in_payload(
    *,
    payload_root: Dict[str, Any],
    graph_id_int: int,
    template_node_id: Optional[int],
    new_node_id: Optional[int],
    position_x: Optional[float],
    position_y: Optional[float],
    offset_x: float,
    offset_y: float,
    strip_link_records: bool,
) -> Dict[str, Any]:
    graph_entry = _find_graph_entry(payload_root, graph_id_int)
    nodes_value = graph_entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError(f"节点图 graph_id={int(graph_id_int)} 缺少 nodes 列表字段 '3'。")

    nodes: List[Dict[str, Any]] = [item for item in nodes_value if isinstance(item, dict)]
    if not nodes:
        raise ValueError(f"节点图 graph_id={int(graph_id_int)} 的 nodes 列表为空，无法选择模板节点。")

    node_id_set = _collect_node_ids(nodes)
    chosen_template = _choose_template_node(
        nodes=nodes,
        node_id_set=node_id_set,
        template_node_id=template_node_id,
        strip_link_records=strip_link_records,
    )
    cloned_node = copy.deepcopy(chosen_template)

    if new_node_id is not None:
        allocated_id = int(new_node_id)
        if allocated_id in node_id_set:
            raise ValueError(f"new_node_id={allocated_id} 已存在于该图中")
    else:
        allocated_id = _choose_next_node_id(sorted(node_id_set))

    cloned_node["1"] = [int(allocated_id)]

    template_x = float(chosen_template.get("5") or 0.0)
    template_y = float(chosen_template.get("6") or 0.0)
    cloned_node["5"] = float(position_x) if position_x is not None else float(template_x + float(offset_x))
    cloned_node["6"] = float(position_y) if position_y is not None else float(template_y + float(offset_y))

    if strip_link_records:
        _strip_link_records_from_node(node=cloned_node, node_id_set=node_id_set)

    nodes_value.append(cloned_node)

    return {
        "graph_id_int": int(graph_id_int),
        "template_node_id": _first_int(chosen_template.get("1")),
        "new_node_id": int(allocated_id),
        "nodes_count_before": len(nodes),
        "nodes_count_after": len([item for item in nodes_value if isinstance(item, dict)]),
    }


def write_back_modified_gil_by_reencoding_payload(
    *,
    raw_dump_object: Dict[str, Any],
    input_gil_path: Path,
    output_gil_path: Path,
) -> None:
    payload_root = _get_payload_root(raw_dump_object)
    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_gil_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="对 .gil 的节点图（payload field 10）追加一个节点，并写回输出新 .gil（基于 DLL dump-json + 自研 encoder）。",
    )
    argument_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    argument_parser.add_argument("output_gil_file", help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）")
    argument_parser.add_argument("--graph-id", dest="graph_id_int", required=True, type=int, help="目标 graph_id（int）")
    argument_parser.add_argument("--template-node-id", dest="template_node_id", type=int, default=None, help="可选：指定克隆的模板 node_id")
    argument_parser.add_argument("--new-node-id", dest="new_node_id", type=int, default=None, help="可选：指定新增 node_id（默认自动分配）")
    argument_parser.add_argument("--pos-x", dest="pos_x", type=float, default=None, help="可选：新增节点坐标 x（不填则按 offset 偏移）")
    argument_parser.add_argument("--pos-y", dest="pos_y", type=float, default=None, help="可选：新增节点坐标 y（不填则按 offset 偏移）")
    argument_parser.add_argument("--offset-x", dest="offset_x", type=float, default=220.0, help="默认偏移 x（pos-x 未指定时生效）")
    argument_parser.add_argument("--offset-y", dest="offset_y", type=float, default=0.0, help="默认偏移 y（pos-y 未指定时生效）")
    argument_parser.add_argument(
        "--keep-link-records",
        dest="keep_link_records",
        action="store_true",
        help="默认会剔除克隆节点中的连线/引用 record；传入该开关则保留。",
    )
    argument_parser.add_argument(
        "--connect-flow-from-node-id",
        dest="connect_flow_from_node_id",
        type=int,
        default=None,
        help=(
            "可选：在新增节点后，额外写回一条 flow 连线。"
            "做法：从该源节点上找到一条指向“模板节点(template_node_id)”的 flow record，克隆并改为指向新节点。"
        ),
    )
    argument_parser.add_argument(
        "--connect-flow-like-dst-node-id",
        dest="connect_flow_like_dst_node_id",
        type=int,
        default=None,
        help="可选：flow 连线模板的目标节点ID（默认使用 template_node_id）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    input_gil_path = Path(arguments.input_gil_file)
    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))

    raw_dump_object = _dump_gil_to_raw_json_object(input_gil_path)
    payload_root = _get_payload_root(raw_dump_object)

    add_report = add_node_to_graph_in_payload(
        payload_root=payload_root,
        graph_id_int=int(arguments.graph_id_int),
        template_node_id=(int(arguments.template_node_id) if arguments.template_node_id is not None else None),
        new_node_id=(int(arguments.new_node_id) if arguments.new_node_id is not None else None),
        position_x=(float(arguments.pos_x) if arguments.pos_x is not None else None),
        position_y=(float(arguments.pos_y) if arguments.pos_y is not None else None),
        offset_x=float(arguments.offset_x),
        offset_y=float(arguments.offset_y),
        strip_link_records=(not bool(arguments.keep_link_records)),
    )

    link_report: Dict[str, Any] = {}
    if arguments.connect_flow_from_node_id is not None:
        graph_entry = _find_graph_entry(payload_root, int(arguments.graph_id_int))
        template_dst_node_id_int = (
            int(arguments.connect_flow_like_dst_node_id)
            if arguments.connect_flow_like_dst_node_id is not None
            else int(add_report.get("template_node_id") or 0)
        )
        if int(template_dst_node_id_int) <= 0:
            raise ValueError("无法推断 connect-flow 模板目标节点：请显式传入 --connect-flow-like-dst-node-id")
        link_report = add_flow_link_by_cloning_template_record(
            graph_entry=graph_entry,
            src_node_id_int=int(arguments.connect_flow_from_node_id),
            template_dst_node_id_int=int(template_dst_node_id_int),
            new_dst_node_id_int=int(add_report["new_node_id"]),
        )

    write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_gil_path,
        output_gil_path=output_gil_path,
    )

    print("=" * 80)
    print("节点图写回完成：")
    for key in sorted(add_report.keys()):
        print(f"- {key}: {add_report.get(key)}")
    if link_report:
        print("- link: ")
        for key in sorted(link_report.keys()):
            print(f"  - {key}: {link_report.get(key)}")
    print(f"- output: {output_gil_path.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()



