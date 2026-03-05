from __future__ import annotations

"""
create_node_graph_in_gil.py

目标：
- 在 `.gil` 的节点图段（payload field 10）中新建一张节点图（GraphEntry），并写回输出新的 `.gil`。

实现策略（最小可行闭环）：
- 使用 dump-json（数值键结构）做 gil -> raw JSON
- 在 dump-json 的 payload(root['4']) 内定位节点图段 `10`
- 从现有 GraphEntry 克隆一个模板（以保证未知字段与编码细节尽量保持一致）
- 修改 header 中的 graph_id（header['5']），修改图名（entry['2']），默认清空 nodes（entry['3']）
- 使用 `gil_dump_codec.encode_message` 重编码 payload 并按原容器 header/footer 封装写回

注意：
- 本脚本仅负责“新增一张图（GraphEntry）”本体；不会自动把新 graph_id 挂载到技能/预设等引用处。
- 不使用 try/except；失败应直接抛错，便于定位。
"""

import argparse
import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, parse_binary_data_hex_text
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


def _iter_graph_groups(node_graph_section: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    迭代节点图段内的“graph group”对象。

    当前样本形态：
    - payload['10'] 为 dict
    - payload['10']['1'] 为 list[dict]（每个 dict 内通常仅包含 key '1'：GraphEntry 列表）
    """
    groups_value = node_graph_section.get("1")
    if isinstance(groups_value, list):
        return [item for item in groups_value if isinstance(item, dict)]
    if isinstance(groups_value, dict):
        return [groups_value]
    return []


def _ensure_graph_groups_list(node_graph_section: Dict[str, Any]) -> List[Any]:
    """
    返回 node_graph_section['1'] 的可变 list 引用，用于追加新的 group。
    """
    groups_value = node_graph_section.get("1")
    if isinstance(groups_value, list):
        return groups_value
    if isinstance(groups_value, dict):
        node_graph_section["1"] = [groups_value]
        return node_graph_section["1"]
    if groups_value is None:
        node_graph_section["1"] = []
        return node_graph_section["1"]
    raise ValueError(f"node_graph_section['1'] 期望为 list/dict/None，但收到: {type(groups_value).__name__}")


def _iter_graph_entries_for_group(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries_value = group.get("1")
    if isinstance(entries_value, list):
        return [item for item in entries_value if isinstance(item, dict)]
    if isinstance(entries_value, dict):
        return [entries_value]
    return []


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


def _is_probable_link_record(*, record_bytes: bytes, node_id_set: set[int]) -> bool:
    decoded = decode_bytes_to_python(record_bytes)
    if not isinstance(decoded, dict):
        return False
    other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
    if not isinstance(other_node_id, int):
        return False
    return int(other_node_id) in node_id_set


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


def _choose_seed_node_from_template_entry(
    *,
    template_entry: Dict[str, Any],
    seed_template_node_id: Optional[int],
    strip_link_records: bool,
) -> Dict[str, Any]:
    nodes_value = template_entry.get("3")
    if not isinstance(nodes_value, list):
        raise ValueError("模板节点图 entry['3'] 缺少 nodes 列表，无法 seed 节点。")
    nodes: List[Dict[str, Any]] = [item for item in nodes_value if isinstance(item, dict)]
    if not nodes:
        raise ValueError("模板节点图 nodes 为空，无法 seed 节点。")

    node_id_set: set[int] = set()
    for node in nodes:
        node_id = _first_int(node.get("1"))
        if isinstance(node_id, int):
            node_id_set.add(int(node_id))

    chosen = None
    if seed_template_node_id is not None:
        target = int(seed_template_node_id)
        for node in nodes:
            node_id = _first_int(node.get("1"))
            if isinstance(node_id, int) and int(node_id) == target:
                chosen = node
                break
        if chosen is None:
            raise ValueError(f"未找到 seed_template_node_id={target}")
    else:
        chosen = nodes[0]

    new_node = copy.deepcopy(chosen)
    if strip_link_records:
        _strip_link_records_from_node(node=new_node, node_id_set=node_id_set)
    return new_node


def _get_graph_id_from_entry(graph_entry: Dict[str, Any]) -> Optional[int]:
    header = _first_dict(graph_entry.get("1"))
    if isinstance(header, dict) and isinstance(header.get("5"), int):
        return int(header.get("5"))
    return None


def _get_graph_name_from_entry(graph_entry: Dict[str, Any]) -> str:
    name_value = graph_entry.get("2")
    if isinstance(name_value, list) and name_value and isinstance(name_value[0], str):
        return str(name_value[0])
    if isinstance(name_value, str):
        return str(name_value)
    return ""


def _infer_graph_scope_mask(graph_id_int: int) -> int:
    return int(graph_id_int) & 0xFF800000


def _collect_existing_graph_ids(payload_root: Dict[str, Any]) -> List[int]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return []
    ids: List[int] = []
    for group in _iter_graph_groups(section):
        for entry in _iter_graph_entries_for_group(group):
            graph_id = _get_graph_id_from_entry(entry)
            if isinstance(graph_id, int):
                ids.append(int(graph_id))
    return ids


def _count_graph_entries(payload_root: Dict[str, Any]) -> int:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        return 0
    total = 0
    for group in _iter_graph_groups(section):
        total += len(_iter_graph_entries_for_group(group))
    return int(total)


def _choose_next_graph_id(*, existing_graph_ids: Sequence[int], scope_mask: int) -> int:
    candidates = [int(v) for v in existing_graph_ids if isinstance(v, int) and (int(v) & 0xFF800000) == int(scope_mask)]
    if not candidates:
        # 若同 scope 下没有任何现有图，则从 scope|1 起步
        candidate = int(scope_mask) | 1
        while candidate in set(int(v) for v in existing_graph_ids if isinstance(v, int)):
            candidate += 1
        return candidate
    candidate = max(candidates) + 1
    existing_set = set(int(v) for v in existing_graph_ids if isinstance(v, int))
    while candidate in existing_set:
        candidate += 1
    return int(candidate)


def _ensure_group_entries_list(group: Dict[str, Any]) -> List[Any]:
    entries_value = group.get("1")
    if isinstance(entries_value, list):
        return entries_value
    if isinstance(entries_value, dict):
        group["1"] = [entries_value]
        return group["1"]
    if entries_value is None:
        group["1"] = []
        return group["1"]
    raise ValueError(f"graph group['1'] 期望为 list/dict/None，但收到: {type(entries_value).__name__}")


def _find_template_entry(
    *,
    payload_root: Dict[str, Any],
    template_graph_id_int: Optional[int],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        raise ValueError("当前存档缺少节点图段 payload['10']，无法从零构建新图。")

    groups = _iter_graph_groups(section)
    if not groups:
        raise ValueError("节点图段 payload['10']['1'] 为空，无法选择模板图。")

    if template_graph_id_int is None:
        # 默认用第一张图作为模板
        for group in groups:
            entries = _iter_graph_entries_for_group(group)
            if entries:
                return group, entries[0]
        raise ValueError("节点图段中未找到任何 GraphEntry 作为模板。")

    target = int(template_graph_id_int)
    for group in groups:
        for entry in _iter_graph_entries_for_group(group):
            graph_id = _get_graph_id_from_entry(entry)
            if isinstance(graph_id, int) and int(graph_id) == target:
                return group, entry
    raise ValueError(f"未找到 template_graph_id={target}")


def create_node_graph_in_payload(
    *,
    payload_root: Dict[str, Any],
    new_graph_name: str,
    template_graph_id_int: Optional[int],
    new_graph_id_int: Optional[int],
    clone_nodes: bool,
    seed_one_node: bool,
    seed_template_node_id: Optional[int],
) -> Dict[str, Any]:
    section = payload_root.get("10")
    if not isinstance(section, dict):
        raise ValueError("当前存档缺少节点图段 payload['10']，无法新增节点图。")

    template_group, template_entry = _find_template_entry(
        payload_root=payload_root,
        template_graph_id_int=template_graph_id_int,
    )
    template_graph_id = _get_graph_id_from_entry(template_entry)
    if not isinstance(template_graph_id, int):
        raise ValueError("模板 GraphEntry 缺少 header['5'] graph_id")

    existing_graph_ids = _collect_existing_graph_ids(payload_root)
    scope_mask = _infer_graph_scope_mask(int(template_graph_id))

    if new_graph_id_int is not None:
        allocated_graph_id = int(new_graph_id_int)
        if allocated_graph_id in set(int(v) for v in existing_graph_ids):
            raise ValueError(f"new_graph_id={allocated_graph_id} 已存在于该存档中")
    else:
        allocated_graph_id = _choose_next_graph_id(existing_graph_ids=existing_graph_ids, scope_mask=scope_mask)

    new_entry = copy.deepcopy(template_entry)

    # header['5'] = new graph_id
    header = _first_dict(new_entry.get("1"))
    if not isinstance(header, dict):
        raise ValueError("模板 GraphEntry 缺少 header（entry['1']）")
    header["5"] = int(allocated_graph_id)

    # entry['2'] = [name]
    name_text = str(new_graph_name or "").strip()
    if name_text == "":
        raise ValueError("new_graph_name 不能为空")
    name_value = new_entry.get("2")
    if isinstance(name_value, list):
        new_entry["2"] = [name_text]
    else:
        # 为稳妥起见统一写成 list（样本中为 list）
        new_entry["2"] = [name_text]

    if bool(clone_nodes):
        pass
    elif bool(seed_one_node):
        seed_node = _choose_seed_node_from_template_entry(
            template_entry=template_entry,
            seed_template_node_id=seed_template_node_id,
            strip_link_records=True,
        )
        new_entry["3"] = [seed_node]
    else:
        # 默认清空 nodes，构建“空图”
        new_entry["3"] = []

    # 重要：实际样本中 section['7'] 与 section['1'] 的“group 数量”保持一致，且每个 group 通常只包含 1 张图。
    # 若把多张图塞进同一个 group，编辑器侧可能只加载最后一张，造成“旧图消失”的错觉。
    #
    # 因此这里采用“一图一个 group”的追加方式：克隆模板 group 的元数据，但将其 graphs 列表替换为 [new_entry]。
    groups_list = _ensure_graph_groups_list(section)
    group_count_before = len([item for item in groups_list if isinstance(item, dict)])

    new_group: Dict[str, Any] = {}
    for key, value in template_group.items():
        if key == "1":
            continue
        new_group[str(key)] = copy.deepcopy(value)
    new_group["1"] = [new_entry]
    groups_list.append(new_group)

    group_count_after = len([item for item in groups_list if isinstance(item, dict)])

    # 同步 section['7']（经验：为节点图 group 数 / 图数量计数）
    section["7"] = int(group_count_after)
    section_count_after = int(section.get("7") if isinstance(section.get("7"), int) else group_count_after)

    return {
        "template_graph_id_int": int(template_graph_id),
        "template_graph_name": _get_graph_name_from_entry(template_entry),
        "new_graph_id_int": int(allocated_graph_id),
        "new_graph_name": name_text,
        "section_7_after": int(section_count_after),
        "group_count_before": int(group_count_before),
        "group_count_after": int(group_count_after),
        "graph_count_after": int(_count_graph_entries(payload_root)),
        "clone_nodes": bool(clone_nodes),
        "seed_one_node": bool(seed_one_node),
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
        description="在 .gil 的节点图段（payload field 10）中新增一张节点图，并写回输出新 .gil。",
    )
    argument_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    argument_parser.add_argument("output_gil_file", help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）")
    argument_parser.add_argument("--new-graph-name", dest="new_graph_name", required=True, help="新节点图名称（显示名）")
    argument_parser.add_argument(
        "--template-graph-id",
        dest="template_graph_id_int",
        type=int,
        default=None,
        help="可选：模板 graph_id（不填则使用节点图段中的第一张图作为模板）。",
    )
    argument_parser.add_argument(
        "--new-graph-id",
        dest="new_graph_id_int",
        type=int,
        default=None,
        help="可选：新图 graph_id（不填则按模板 scope 自动分配）。",
    )
    argument_parser.add_argument(
        "--clone-nodes",
        dest="clone_nodes",
        action="store_true",
        help="可选：是否连同 nodes 一并克隆（默认清空 nodes 生成空图）。",
    )
    argument_parser.add_argument(
        "--seed-one-node",
        dest="seed_one_node",
        action="store_true",
        help="可选：不克隆整张图，只从模板图里克隆一个节点作为起始节点（会剔除疑似连线 record）。",
    )
    argument_parser.add_argument(
        "--seed-template-node-id",
        dest="seed_template_node_id",
        type=int,
        default=None,
        help="可选：seed 时从模板图选择哪个 node_id（不填则取模板 nodes[0]）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    input_gil_path = Path(arguments.input_gil_file)
    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))

    raw_dump_object = _dump_gil_to_raw_json_object(input_gil_path)
    payload_root = _get_payload_root(raw_dump_object)

    report = create_node_graph_in_payload(
        payload_root=payload_root,
        new_graph_name=str(arguments.new_graph_name),
        template_graph_id_int=(int(arguments.template_graph_id_int) if arguments.template_graph_id_int is not None else None),
        new_graph_id_int=(int(arguments.new_graph_id_int) if arguments.new_graph_id_int is not None else None),
        clone_nodes=bool(arguments.clone_nodes),
        seed_one_node=bool(arguments.seed_one_node),
        seed_template_node_id=(int(arguments.seed_template_node_id) if arguments.seed_template_node_id is not None else None),
    )

    write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_gil_path,
        output_gil_path=output_gil_path,
    )

    print("=" * 80)
    print("新建节点图写回完成：")
    for key in sorted(report.keys()):
        print(f"- {key}: {report.get(key)}")
    print(f"- output: {output_gil_path.resolve()}")
    print("=" * 80)


if __name__ == "__main__":
    main()




