from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.node_graph.gia_graph_ir import read_graph_irs_from_gia_file
from ugc_file_tools.node_data_index import resolve_default_node_data_index_path
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


def export_readable_graph_ir_from_gia_file(
    gia_file_path: Path,
    *,
    output_dir: Path,
    node_data_index_path: Path,
    check_header: bool = False,
    write_markdown: bool = True,
    max_depth: int = 16,
) -> dict[str, Any]:
    gia_file_path = Path(gia_file_path).resolve()
    if not gia_file_path.is_file():
        raise FileNotFoundError(f"input gia file not found: {str(gia_file_path)!r}")

    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gia_graph_ir")
    graphs_json_dir = output_dir / "graphs"
    graphs_markdown_dir = output_dir / "graphs_markdown"
    _ensure_directory(graphs_json_dir)
    if write_markdown:
        _ensure_directory(graphs_markdown_dir)

    graph_irs = read_graph_irs_from_gia_file(
        gia_file_path,
        node_data_index_path=Path(node_data_index_path),
        check_header=bool(check_header),
        decode_max_depth=int(max_depth),
    )

    exported_index: list[dict[str, Any]] = []
    for graph_ir in graph_irs:
        unit_index = int(graph_ir.get("unit_index", 0) or 0)
        graph_id_int = int(graph_ir.get("graph_id_int", 0) or 0)
        graph_name = str(graph_ir.get("graph_name") or "").strip()
        output_file_stem = _sanitize_filename(
            f"gia_graph_ir_{graph_id_int}_{graph_name}",
            max_length=140,
        )

        json_output_path = graphs_json_dir / f"{output_file_stem}.json"
        _write_json_file(json_output_path, graph_ir)

        markdown_output_path = graphs_markdown_dir / f"{output_file_stem}.md"
        if write_markdown:
            md: list[str] = []
            md.append(f"## GIA 节点图 IR：{graph_name}")
            md.append("")
            md.append(f"- unit_index: {unit_index}")
            md.append(f"- graph_id_int: {graph_id_int}")
            md.append(f"- scope: {graph_ir.get('graph_scope')}")
            md.append(f"- node_count: {graph_ir.get('node_count')}")
            md.append(f"- graph_variables: {len(graph_ir.get('graph_variables') or [])}")
            md.append(f"- source_gia_file: `{gia_file_path}`")
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
                "unit_index": unit_index,
                "graph_id_int": graph_id_int,
                "graph_name": graph_name,
                "graph_scope": str(graph_ir.get("graph_scope") or ""),
                "node_count": int(graph_ir.get("node_count") or 0),
                "edges_count": len(graph_ir.get("edges") or []),
                "ir_json": str(json_output_path.relative_to(output_dir)).replace("\\", "/"),
                "ir_markdown": (
                    str(markdown_output_path.relative_to(output_dir)).replace("\\", "/") if write_markdown else None
                ),
            }
        )

    index_path = output_dir / "index.json"
    _write_json_file(index_path, exported_index)

    return {
        "source_gia_file": str(gia_file_path),
        "output_dir": str(output_dir),
        "graphs_count": len(exported_index),
        "index": str(index_path),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="解析 .gia 节点图为可读 IR（解析语义统一复用 ugc_file_tools.graph.node_graph）。"
    )
    argument_parser.add_argument(
        "--input-gia",
        dest="input_gia_file",
        required=True,
        help="输入 .gia 文件路径（节点图 .gia，例如 元件库/压力板.gia）",
    )
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="gia_graph_ir",
        help="输出目录（默认：gia_graph_ir；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    argument_parser.add_argument(
        "--node-data-index",
        dest="node_data_index",
        default=str(resolve_default_node_data_index_path()),
        help="节点数据索引 index.json 路径（默认：ugc_file_tools/node_data/index.json）",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 .gia 容器头/尾（失败会直接抛错）。",
    )
    argument_parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="protobuf 递归解码深度上限（默认 16）。",
    )
    argument_parser.add_argument(
        "--no-markdown",
        dest="no_markdown",
        action="store_true",
        help="仅导出 JSON IR，不生成 Markdown 摘要。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = export_readable_graph_ir_from_gia_file(
        Path(arguments.input_gia_file),
        output_dir=Path(arguments.output_dir),
        node_data_index_path=Path(arguments.node_data_index),
        check_header=bool(arguments.check_header),
        write_markdown=(not bool(arguments.no_markdown)),
        max_depth=int(arguments.max_depth),
    )

    print("=" * 80)
    print("GIA 节点图 IR 导出完成：")
    print(f"- source_gia_file: {result.get('source_gia_file')}")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- graphs_count: {result.get('graphs_count')}")
    print(f"- index: {result.get('index')}")
    print("=" * 80)


if __name__ == "__main__":
    from ugc_file_tools.unified_cli.entry_guard import deny_direct_execution

    deny_direct_execution(tool_name="parse_gia_to_graph_ir")

