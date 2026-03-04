from __future__ import annotations

"""
create_type_id_list_graph_in_gil.py

目标：
- 在一个现有 `.gil` 文件中新增一张“type_id 列表图”（GraphEntry），用于批量制造节点样本：
  - 图中节点按从左到右、从上到下排列；
  - 每个节点强制写入一个指定的 node_type_id_int（即节点 type_id）；
  - 默认不连线、默认清空 records，尽量避免携带旧引用。

用途：
- 与 `create_type_id_matrix_in_gil.py`（连续区间矩阵）互补：
  - 当 type_id 集合不是连续区间（例如来自 node_data/index.json 的 Server 节点），用本脚本更合适；
  - 可生成“全节点样本库图”，你在编辑器/游戏内打开后再导出，可获得更完整的节点 record 结构样本。

注意：
- 不使用 try/except；失败直接抛错，便于定位。
- 输出路径强制写入 `ugc_file_tools/out/`。
"""

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.commands.create_type_id_matrix_in_gil import (
    choose_next_graph_id as _choose_next_graph_id,
    choose_template_node_for_matrix as _choose_template_node_for_matrix,
    collect_existing_graph_ids as _collect_existing_graph_ids,
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    ensure_list as _ensure_list,
    find_graph_entry as _find_graph_entry,
    first_dict as _first_dict,
    get_payload_root as _get_payload_root,
    patch_node_type_id_in_binary_text as _patch_node_type_id_in_binary_text,
    iter_graph_groups as _iter_graph_groups,
    iter_graph_entries_for_group as _iter_graph_entries_for_group,
)
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import ugc_file_tools_root


def _normalize_range_filter(text: str) -> str:
    t = str(text or "").strip().lower()
    if t in ("", "both", "all"):
        return ""
    if t in ("server", "s"):
        return "server"
    if t in ("client", "c"):
        return "client"
    raise ValueError(f"node_data_range 不支持：{text!r}（可选：server/client/both）")


def _load_type_ids_from_node_data(*, node_data_range: str) -> List[int]:
    range_filter = _normalize_range_filter(node_data_range)
    index_path = ugc_file_tools_root() / "node_data" / "index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"node_data/index.json not found: {str(index_path)!r}")
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("node_data/index.json is not a dict document")
    nodes = doc.get("NodesList")
    if not isinstance(nodes, list):
        raise ValueError("node_data/index.json 缺少 NodesList(list)")

    ids: List[int] = []
    for entry in nodes:
        if not isinstance(entry, dict):
            continue
        node_id = entry.get("ID")
        if not isinstance(node_id, int):
            continue
        if range_filter:
            r = str(entry.get("Range") or "").strip().lower()
            if r != range_filter:
                continue
        ids.append(int(node_id))

    # 去重并排序，保证输出稳定
    return sorted(set(int(v) for v in ids))


def _load_type_ids_from_json_list_file(path: Path) -> List[int]:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        raise ValueError("type_ids_json 必须是 JSON list[int]")
    ids: List[int] = []
    for item in obj:
        if isinstance(item, int):
            ids.append(int(item))
            continue
        if isinstance(item, str) and item.strip().isdigit():
            ids.append(int(item.strip()))
            continue
        raise ValueError(f"type_ids_json 含非法元素（期望 int）：{item!r}")
    return sorted(set(int(v) for v in ids))


def create_type_id_list_graph(
    *,
    input_gil_path: Path,
    output_gil_path: Path,
    template_graph_id_int: int,
    new_graph_name: str,
    type_ids: List[int],
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
        raise ValueError("输入 .gil 缺少节点图段 payload['10']（请改用包含节点图段的基底存档）")

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

    ids = [int(v) for v in type_ids if isinstance(v, int)]
    if not ids:
        raise ValueError("type_ids 为空")
    cols = int(columns)
    if cols <= 0:
        raise ValueError("columns 必须 > 0")

    # 新图 graph_id（与模板图同 scope）
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
        name_text = "type_id_list_graph"
    new_entry["2"] = [name_text]

    new_nodes: List[Dict[str, Any]] = []
    for i, type_id_int in enumerate(ids, start=1):
        node_id_int = int(i)
        col = int((i - 1) % cols)
        row = int((i - 1) // cols)
        x = float(origin_x_value + float(col) * float(spacing_x))
        y = float(origin_y_value + float(row) * float(spacing_y))

        node_obj = copy.deepcopy(template_node)
        node_obj["1"] = [node_id_int]
        node_obj["5"] = float(x)
        node_obj["6"] = float(y)
        node_obj["4"] = []

        # 强制写入 type_id：同时改 data_2 与 data_3
        node_obj["2"] = _patch_node_type_id_in_binary_text(str(node_obj.get("2")), int(type_id_int))
        node_obj["3"] = _patch_node_type_id_in_binary_text(str(node_obj.get("3")), int(type_id_int))

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
        "nodes_written": int(len(ids)),
        "columns": int(cols),
        "spacing_x": float(spacing_x),
        "spacing_y": float(spacing_y),
        "origin_x": float(origin_x_value),
        "origin_y": float(origin_y_value),
        "type_id_count": int(len(ids)),
        "type_id_min": int(min(ids)),
        "type_id_max": int(max(ids)),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="在 .gil 内新增一张 type_id 列表图（用于批量制造节点样本/校准映射）。")
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径（必须包含节点图段 payload['10']）")
    parser.add_argument("output_gil_file", help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）")
    parser.add_argument("--template-graph-id", dest="template_graph_id_int", type=int, required=True, help="用于克隆结构的模板 graph_id_int")
    parser.add_argument("--new-graph-name", dest="new_graph_name", default="", help="新图名称（默认 type_id_list_graph）")
    parser.add_argument("--columns", dest="columns", type=int, default=20, help="每行列数（默认 20）")
    parser.add_argument("--spacing-x", dest="spacing_x", type=float, default=520.0, help="横向间距（默认 520）")
    parser.add_argument("--spacing-y", dest="spacing_y", type=float, default=340.0, help="纵向间距（默认 340）")
    parser.add_argument("--origin-x", dest="origin_x", type=float, default=None, help="起始 x 坐标（默认取模板节点 x）")
    parser.add_argument("--origin-y", dest="origin_y", type=float, default=None, help="起始 y 坐标（默认取模板节点 y）")

    src_group = parser.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--from-node-data", dest="from_node_data", action="store_true", help="从 ugc_file_tools/node_data/index.json 读取 type_id 列表")
    src_group.add_argument("--type-ids-json", dest="type_ids_json", default=None, help="JSON list[int] 文件路径（自定义 type_id 列表）")
    parser.add_argument(
        "--node-data-range",
        dest="node_data_range",
        default="server",
        help="当 --from-node-data 时生效：server/client/both（默认 server）",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if bool(args.from_node_data):
        type_ids = _load_type_ids_from_node_data(node_data_range=str(args.node_data_range))
    else:
        type_ids = _load_type_ids_from_json_list_file(Path(str(args.type_ids_json)))

    report = create_type_id_list_graph(
        input_gil_path=Path(args.input_gil_file),
        output_gil_path=resolve_output_file_path_in_out_dir(Path(args.output_gil_file)),
        template_graph_id_int=int(args.template_graph_id_int),
        new_graph_name=str(args.new_graph_name),
        type_ids=list(type_ids),
        columns=int(args.columns),
        spacing_x=float(args.spacing_x),
        spacing_y=float(args.spacing_y),
        origin_x=(float(args.origin_x) if args.origin_x is not None else None),
        origin_y=(float(args.origin_y) if args.origin_y is not None else None),
    )

    print("=" * 80)
    print("type_id 列表图已生成：")
    for key in sorted(report.keys()):
        print(f"- {key}: {report.get(key)}")
    print("=" * 80)


if __name__ == "__main__":
    main()




