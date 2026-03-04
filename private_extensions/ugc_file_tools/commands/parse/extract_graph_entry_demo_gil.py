from __future__ import annotations

"""
extract_graph_entry_demo_gil.py

目标：
- 从一个已有 `.gil` 中“抽取/裁剪”出更适合作为示范的节点图：
  - 可选：清空 nodes（GraphEntry['3']），用于保留变量表/结构体定义/信号定义等“管理配置”示范；
  - 可选：仅保留指定名称的节点图变量（GraphEntry['6']），避免示范存档混入无关变量；
  - 其余段保持不变（尽量减少对真源兼容性的破坏）。

说明：
- 该工具的定位是“示范存档制作器”，不是通用压缩器；不会尝试删除未知段。
- 不使用 try/except；失败直接抛错，便于定位。
"""

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from ugc_file_tools.node_graph_writeback.gil_dump import find_graph_entry, get_payload_root


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


def _iter_graph_ids(payload_root: Dict[str, Any]) -> List[int]:
    sec10 = payload_root.get("10")
    if not isinstance(sec10, dict):
        return []
    groups = sec10.get("1")
    groups_list = groups if isinstance(groups, list) else [groups] if isinstance(groups, dict) else []
    out: List[int] = []
    for g in groups_list:
        if not isinstance(g, dict):
            continue
        entries = g.get("1")
        entries_list = entries if isinstance(entries, list) else [entries] if isinstance(entries, dict) else []
        for e in entries_list:
            if not isinstance(e, dict):
                continue
            header_value = e.get("1")
            header_obj = (
                header_value[0]
                if isinstance(header_value, list) and header_value and isinstance(header_value[0], dict)
                else header_value
            )
            if not isinstance(header_obj, dict):
                continue
            gid = header_obj.get("5")
            if isinstance(gid, int):
                out.append(int(gid))
    return out


def _drop_other_graph_entries_inplace(*, payload_root: Dict[str, Any], keep_graph_id_int: int) -> int:
    """
    真正裁剪“节点图段”：只保留指定 graph_id 的 GraphEntry，其它 GraphEntry 全部移除。

    注意：
    - 该操作只裁剪 payload['10'] 的 graph groups/entries；
    - 不会尝试清理 section10 外的未知引用段（该工具不是通用压缩器）。
    """
    sec10 = payload_root.get("10")
    if not isinstance(sec10, dict):
        raise ValueError("payload_root 缺少节点图段 '10'")
    groups_value = sec10.get("1")
    groups_list = groups_value if isinstance(groups_value, list) else [groups_value] if isinstance(groups_value, dict) else []
    kept_entries: List[Dict[str, Any]] = []
    for g in list(groups_list):
        if not isinstance(g, dict):
            continue
        entries_value = g.get("1")
        entries_list = (
            entries_value
            if isinstance(entries_value, list)
            else [entries_value]
            if isinstance(entries_value, dict)
            else []
        )
        for e in list(entries_list):
            if not isinstance(e, dict):
                continue
            header_value = e.get("1")
            header_obj = (
                header_value[0]
                if isinstance(header_value, list) and header_value and isinstance(header_value[0], dict)
                else header_value
            )
            gid = header_obj.get("5") if isinstance(header_obj, dict) else None
            if isinstance(gid, int) and int(gid) == int(keep_graph_id_int):
                kept_entries.append(e)
    if not kept_entries:
        raise ValueError(f"未在节点图段中找到目标 graph_id={int(keep_graph_id_int)}，无法裁剪。")

    # 保持结构稳定：写回为单 group + entries list（避免空 group/多 group 形态漂移）
    sec10["1"] = [{"1": list(kept_entries)}]
    return int(len(kept_entries))


def extract_demo_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    graph_id_int: Optional[int],
    clear_nodes: bool,
    keep_var_names: Optional[List[str]],
    drop_other_graphs: bool,
) -> Dict[str, Any]:
    raw_dump_object = _dump_gil_to_raw_json_object(Path(input_gil_file_path))
    payload_root = get_payload_root(raw_dump_object)

    graph_ids = _iter_graph_ids(payload_root)
    if not graph_ids:
        raise ValueError("输入 .gil 不包含节点图段/graph entries，无法抽取示范图。")

    target_graph_id = int(graph_id_int) if graph_id_int is not None else int(graph_ids[0])
    entry = find_graph_entry(payload_root, int(target_graph_id))

    kept_graph_entries = None
    if bool(drop_other_graphs):
        kept_graph_entries = _drop_other_graph_entries_inplace(
            payload_root=payload_root,
            keep_graph_id_int=int(target_graph_id),
        )

    if bool(clear_nodes):
        entry["3"] = []

    kept_names: Optional[List[str]] = None
    if keep_var_names is not None:
        kept_names = [str(x).strip() for x in list(keep_var_names) if str(x).strip() != ""]
        if not kept_names:
            kept_names = None

    if kept_names is not None:
        vars_value = entry.get("6")
        if not isinstance(vars_value, list):
            vars_value = []
        filtered: List[Dict[str, Any]] = []
        for item in vars_value:
            if not isinstance(item, dict):
                continue
            name = item.get("2")
            if isinstance(name, str) and name in set(kept_names):
                filtered.append(item)
        entry["6"] = filtered

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(Path(input_gil_file_path))
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(Path(input_gil_file_path).resolve()),
        "output_gil": str(output_path),
        "graph_id_int": int(target_graph_id),
        "clear_nodes": bool(clear_nodes),
        "kept_var_names": list(kept_names) if kept_names is not None else [],
        "kept_var_count": int(len(entry.get("6") or [])) if isinstance(entry.get("6"), list) else 0,
        "drop_other_graphs": bool(drop_other_graphs),
        "kept_graph_entries": int(kept_graph_entries) if isinstance(kept_graph_entries, int) else None,
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="抽取/裁剪一个 .gil 的节点图，用于制作“最小示范存档”。")
    parser.add_argument("--input-gil", required=True, help="输入 .gil 文件路径")
    parser.add_argument(
        "--output-gil",
        default="demo_extract_graph_entry.gil",
        help="输出 .gil 文件名/路径（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument("--graph-id", type=int, default=None, help="可选：目标 graph_id_int；不填则使用第一张图。")
    parser.add_argument(
        "--keep-nodes",
        action="store_true",
        help="不清空 nodes（默认会清空 nodes，以去掉演示节点/连线）。",
    )
    parser.add_argument(
        "--drop-other-graphs",
        action="store_true",
        help="真正裁剪节点图段：只保留目标 graph_id 的 GraphEntry（默认不裁剪，仍保留其它节点图）。",
    )
    parser.add_argument(
        "--keep-var-name",
        action="append",
        default=None,
        help="可重复：仅保留这些名称的节点图变量（GraphEntry['6']）。不传则保留原变量表。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = extract_demo_gil(
        input_gil_file_path=Path(args.input_gil),
        output_gil_file_path=Path(args.output_gil),
        graph_id_int=(int(args.graph_id) if args.graph_id is not None else None),
        clear_nodes=(not bool(args.keep_nodes)),
        keep_var_names=(list(args.keep_var_name) if args.keep_var_name is not None else None),
        drop_other_graphs=bool(args.drop_other_graphs),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()




