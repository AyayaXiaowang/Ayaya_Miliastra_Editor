from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.package_parser import load_parsed_package


def main(argv: Optional[Iterable[str]] = None) -> None:
    """
    读取项目存档（Graph_Generater/assets/资源库/项目存档/<package>/），
    打印“程序内部 Python 结构”中的节点图摘要（nodes + edges）。

    说明：
    - 该脚本不依赖 IR JSON 文件；它直接走 `package_parser` 加载 dataclass。
    - 用于验证：我们确实已经把 .gil 的节点图反向解析为 Python 结构（含完整连线）。
    """
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="检查项目存档节点图 Python 结构（nodes+edges）。",
    )
    argument_parser.add_argument(
        "--package-root",
        dest="package_root",
        required=True,
        help="项目存档目录（例如 Graph_Generater/assets/资源库/项目存档/test4）",
    )
    argument_parser.add_argument(
        "--graph-id",
        dest="graph_id_int",
        type=int,
        default=0,
        help="可选：只打印指定 graph_id_int 的图（例如 1073741826）。",
    )
    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    package_root = Path(arguments.package_root).resolve()
    parsed = load_parsed_package(package_root)

    graph_id_filter = int(arguments.graph_id_int or 0)
    graphs = parsed.pyugc_node_graphs

    for graph_id_int, graph in sorted(graphs.items(), key=lambda item: item[0]):
        if graph_id_filter and int(graph_id_int) != graph_id_filter:
            continue

        flow_edges = [edge for edge in graph.edges if edge.edge_kind == "flow"]
        data_edges = [edge for edge in graph.edges if edge.edge_kind == "data"]

        print("=" * 80)
        print(f"graph_id_int: {graph.graph_id_int}")
        print(f"graph_name: {graph.graph_name}")
        print(f"nodes: {len(graph.nodes)}")
        print(f"edges_total: {len(graph.edges)} (flow={len(flow_edges)}, data={len(data_edges)})")
        print("=" * 80)

        # 仅打印前若干条边，避免刷屏
        preview_edges = graph.edges[:50]
        for edge in preview_edges:
            print(
                f"- {edge.edge_kind}: "
                f"{edge.src_node_id_int}:{edge.src_port} -> {edge.dst_node_id_int}:{edge.dst_port} "
                f"(record_index={edge.record_index})"
            )

        if len(graph.edges) > len(preview_edges):
            print(f"... {len(graph.edges) - len(preview_edges)} more edges omitted ...")


if __name__ == "__main__":
    main()




