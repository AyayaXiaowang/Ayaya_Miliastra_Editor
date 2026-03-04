from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.node_data_index import (
    resolve_default_node_data_index_path,
)
from ugc_file_tools.graph.node_graph.gil_payload_graph_ir import (
    parse_gil_payload_node_graphs_to_graph_ir,
    read_gil_payload_bytes_and_container_meta,
)
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


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
    Path(target_dir).mkdir(parents=True, exist_ok=True)


def _write_json_file(target_path: Path, payload: Any) -> None:
    Path(target_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_file(target_path: Path, text: str) -> None:
    Path(target_path).write_text(str(text or ""), encoding="utf-8")


def export_readable_graph_ir_from_gil_payload(
    gil_file_path: Path,
    *,
    output_dir: Path,
    node_data_index_path: Path,
    graph_ids: Optional[List[int]] = None,
    write_markdown: bool = True,
    max_depth: int = 16,
) -> Dict[str, Any]:
    _, container_meta = read_gil_payload_bytes_and_container_meta(gil_file_path=Path(gil_file_path))

    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gil_payload_graph_ir")
    graphs_json_dir = output_dir / "graphs"
    graphs_markdown_dir = output_dir / "graphs_markdown"
    _ensure_directory(graphs_json_dir)
    if write_markdown:
        _ensure_directory(graphs_markdown_dir)

    selected_graph_id_set: Optional[set[int]] = None
    if graph_ids:
        selected_graph_id_set = {int(x) for x in graph_ids if isinstance(x, int)}

    exported_index: List[Dict[str, Any]] = []

    parsed = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=Path(gil_file_path),
        node_data_index_path=Path(node_data_index_path),
        graph_ids=(list(selected_graph_id_set) if selected_graph_id_set is not None else None),
        max_depth=int(max_depth),
    )

    for item in parsed:
        group_index = int(item.group_index)
        entry_index = int(item.entry_index)
        graph_id_int = int(item.graph_id_int)
        graph_name = str(item.graph_name or "").strip()
        graph_ir = dict(item.graph_ir)

        output_file_stem = _sanitize_filename(
            f"gil_graph_ir_{graph_id_int}_{graph_name}",
            max_length=140,
        )
        json_output_path = graphs_json_dir / f"{output_file_stem}.json"
        _write_json_file(
            json_output_path,
            {
                **graph_ir,
                "source_gil_file": str(Path(gil_file_path).resolve()),
                "node_graph_blob_meta": {
                    "group_index": group_index,
                    "entry_index": entry_index,
                    "blob_bytes_len": int(item.blob_bytes_len),
                },
                "gil_container": container_meta,
                "node_data_index_path": str(Path(node_data_index_path).resolve()),
                "decode_max_depth": int(max_depth),
            },
        )

        markdown_output_path = graphs_markdown_dir / f"{output_file_stem}.md"
        if write_markdown:
            md: List[str] = []
            md.append(f"## GIL 节点图 IR（payload 直读）：{graph_name}")
            md.append("")
            md.append(f"- graph_id_int: {graph_id_int}")
            md.append(f"- group_index: {group_index}")
            md.append(f"- entry_index: {entry_index}")
            md.append(f"- node_count: {graph_ir.get('node_count')}")
            md.append(f"- graph_variables: {len(graph_ir.get('graph_variables') or [])}")
            md.append(f"- source_gil_file: `{Path(gil_file_path).resolve()}`")
            md.append("")
            md.append("### 节点列表（摘要）")
            md.append("")
            for node_item in sorted(graph_ir.get("nodes") or [], key=lambda x: int(x.get("node_index_int", 0))):
                node_index_int = int(node_item.get("node_index_int", 0) or 0)
                node_type_id_int = node_item.get("node_type_id_int")
                node_type_name = str(node_item.get("node_type_name") or "").strip()
                md.append(f"- node {node_index_int}: type={node_type_id_int} ({node_type_name})")
            md.append("")
            md.append("### 连线（edges）")
            md.append("")
            for edge in graph_ir.get("edges") or []:
                md.append(
                    f"- {edge.get('edge_kind')}: "
                    f"{edge.get('src_node_index_int')}:{edge.get('src_port_index_int')} -> "
                    f"{edge.get('dst_node_index_int')}:{edge.get('dst_port_index_int')}"
                )
            _write_text_file(markdown_output_path, "\n".join(md) + "\n")

        exported_index.append(
            {
                "graph_id_int": graph_id_int,
                "graph_name": graph_name,
                "group_index": group_index,
                "entry_index": entry_index,
                "node_count": int(graph_ir.get("node_count") or 0),
                "edges_count": len(graph_ir.get("edges") or []),
                "ir_json": str(json_output_path.relative_to(output_dir)).replace("\\", "/"),
                "ir_markdown": (
                    str(markdown_output_path.relative_to(output_dir)).replace("\\", "/") if write_markdown else None
                ),
            }
        )

    index_path = output_dir / "index.json"
    _write_json_file(index_path, sorted(exported_index, key=lambda item: int(item.get("graph_id_int", 0))))

    claude_path = output_dir / "claude.md"
    _write_text_file(
        claude_path,
        "\n".join(
            [
                "## 目录用途",
                "- 存放从 `.gil` 的 payload（section10 / 10.1.1 NodeGraph blob）直接解析得到的“可读节点图 IR”（JSON/Markdown）。",
                "",
                "## 当前状态",
                f"- 当前包含 {len(exported_index)} 张节点图的 IR 导出结果。",
                "- `graphs/`：每张图的 JSON IR（nodes/pins/edges/variables/comments）。",
                "- `graphs_markdown/`：每张图的 Markdown 摘要（便于快速阅读）。" if write_markdown else "- 未生成 Markdown 摘要（使用 --no-markdown）。",
                "- `index.json`：图列表索引。",
                "",
                "## 注意事项",
                "- 该导出路径不依赖“导出项目存档/pyugc_graphs”，用于更贴近真源的结构解析与差异定位。",
                "- 为性能考虑：先对 `.gil` payload 做浅层解码定位 blob，再对命中 blob 做深度解码（学习 genshin-ts 的扫描思路）。",
                "- 本目录不记录修改历史，仅保持用途/状态/注意事项的实时描述。",
                "",
                "---",
                "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                "",
            ]
        ),
    )

    return {
        "source_gil_file": str(Path(gil_file_path).resolve()),
        "output_dir": str(output_dir),
        "graphs_count": len(exported_index),
        "index": str(index_path),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="直接解析 .gil 的 payload(section10/10.1.1 NodeGraph blob) 并导出 Graph IR（更贴近 .gia 的 pins/edges 结构）。"
    )
    argument_parser.add_argument("--input-gil", dest="input_gil_file", required=True, help="输入 .gil 文件路径")
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="gil_payload_graph_ir",
        help="输出目录（默认：gil_payload_graph_ir；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    argument_parser.add_argument(
        "--node-data-index",
        dest="node_data_index",
        default=str(resolve_default_node_data_index_path()),
        help="节点数据索引 index.json 路径（默认：ugc_file_tools/node_data/index.json）",
    )
    argument_parser.add_argument(
        "--graph-id",
        dest="graph_ids",
        action="append",
        type=int,
        default=[],
        help="仅导出指定 graph_id_int（可重复传多次）。不传则导出全部。",
    )
    argument_parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="NodeGraph blob 深度解码上限（默认 16）。",
    )
    argument_parser.add_argument(
        "--no-markdown",
        dest="no_markdown",
        action="store_true",
        help="仅导出 JSON IR，不生成 Markdown 摘要。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = export_readable_graph_ir_from_gil_payload(
        Path(arguments.input_gil_file),
        output_dir=Path(arguments.output_dir),
        node_data_index_path=Path(arguments.node_data_index),
        graph_ids=list(arguments.graph_ids or []),
        write_markdown=(not bool(arguments.no_markdown)),
        max_depth=int(arguments.max_depth),
    )

    print("=" * 80)
    print("GIL payload 节点图 IR 导出完成：")
    print(f"- source_gil_file: {result.get('source_gil_file')}")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- graphs_count: {result.get('graphs_count')}")
    print(f"- index: {result.get('index')}")
    print("=" * 80)


if __name__ == "__main__":
    from ugc_file_tools.unified_cli.entry_guard import deny_direct_execution

    deny_direct_execution(tool_name="parse_gil_payload_to_graph_ir")




