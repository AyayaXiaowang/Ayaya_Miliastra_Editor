from __future__ import annotations

"""
CLI thin entry: generate Graph Code from a single pyugc graph json.

说明：
- pyugc → GraphModel 的核心逻辑已下沉到库层 `ugc_file_tools.graph.pyugc_graph_model_builder`（单一真源）
- GraphModel → Graph Code 统一使用 `app.codegen.ExecutableCodeGenerator`（通过 `ugc_file_tools.graph_codegen` 薄转发）
"""

import argparse
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.pyugc_graph_model_builder import (
    build_graph_model_from_pyugc_graph,
    infer_graph_scope_from_id_int,
)
from ugc_file_tools.graph_codegen import ExecutableCodeGenerator
from ugc_file_tools.repo_paths import resolve_graph_generater_root, ugc_file_tools_root


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _diff_graph_models_by_titles_and_ports(*, src_graph: Any, gen_graph: Any) -> dict[str, Any]:
    """弱 diff：按节点标题与端口连线集合对比（忽略 node_id/edge_id/pos）。"""
    from engine.graph.common import is_flow_port

    def node_title_counts(model: Any) -> Counter:
        c: Counter = Counter()
        for n in (getattr(model, "nodes", {}) or {}).values():
            title = str(getattr(n, "title", "") or "").strip()
            if title:
                c[title] += 1
        return c

    def edge_signatures(model: Any) -> Counter:
        c: Counter = Counter()
        nodes = getattr(model, "nodes", {}) or {}
        for e in (getattr(model, "edges", {}) or {}).values():
            src_node = nodes.get(getattr(e, "src_node", ""))
            dst_node = nodes.get(getattr(e, "dst_node", ""))
            if src_node is None or dst_node is None:
                continue
            src_title = str(getattr(src_node, "title", "") or "").strip()
            dst_title = str(getattr(dst_node, "title", "") or "").strip()
            src_port = str(getattr(e, "src_port", "") or "").strip()
            dst_port = str(getattr(e, "dst_port", "") or "").strip()
            if not src_title or not dst_title or not src_port or not dst_port:
                continue
            edge_kind = (
                "flow"
                if (is_flow_port(src_node, src_port, True) or is_flow_port(dst_node, dst_port, False))
                else "data"
            )
            c[(edge_kind, src_title, src_port, dst_title, dst_port)] += 1
        return c

    src_nodes = node_title_counts(src_graph)
    gen_nodes = node_title_counts(gen_graph)
    src_edges = edge_signatures(src_graph)
    gen_edges = edge_signatures(gen_graph)

    return {
        "nodes_only_in_src": src_nodes - gen_nodes,
        "nodes_only_in_generated": gen_nodes - src_nodes,
        "edges_only_in_src": src_edges - gen_edges,
        "edges_only_in_generated": gen_edges - src_edges,
    }


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="从项目存档的 pyugc_graphs 原始结构反向生成可运行 Graph Code（不依赖参考 Graph Code）。",
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
        required=True,
        help="pyugc 节点图 graph_id_int（例如 1073741826）",
    )
    argument_parser.add_argument(
        "--mapping-file",
        dest="mapping_file",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名 映射文件路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )
    argument_parser.add_argument(
        "--output-file",
        dest="output_file",
        default="",
        help="输出 Graph Code 文件路径（默认写入到 <package>/节点图/<scope>/自动解析_节点图_<id>.py）",
    )
    argument_parser.add_argument(
        "--validate",
        dest="validate",
        action="store_true",
        help="生成后使用引擎校验“本次生成的 Graph Code 文件”（静态校验，不执行节点逻辑）。",
    )
    argument_parser.add_argument(
        "--diff",
        dest="diff",
        action="store_true",
        help="生成后将 Graph Code 解析回 GraphModel，并与源 GraphModel 做结构对比（弱同构：按节点标题/端口连线签名对比）。",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    package_root = Path(args.package_root).resolve()
    graph_id_int = int(args.graph_id_int)
    mapping_path = Path(args.mapping_file).resolve()

    if not package_root.is_dir():
        raise FileNotFoundError(f"package_root not found: {str(package_root)!r}")
    if not mapping_path.is_file():
        raise FileNotFoundError(f"mapping file not found: {str(mapping_path)!r}")

    graph_scope = infer_graph_scope_from_id_int(graph_id_int)
    if graph_scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_scope: {graph_scope!r} for graph_id_int={graph_id_int}")

    graph_model, metadata = build_graph_model_from_pyugc_graph(
        package_root=package_root,
        graph_id_int=graph_id_int,
        mapping_path=mapping_path,
    )

    graph_generater_root = resolve_graph_generater_root(package_root)
    import sys

    root_text = str(graph_generater_root.resolve())
    if root_text not in sys.path:
        sys.path.insert(0, root_text)

    codegen = ExecutableCodeGenerator(graph_generater_root.resolve())
    code_text = codegen.generate_code(graph_model, metadata=metadata)

    output_path_text = str(args.output_file or "").strip()
    if output_path_text != "":
        output_file_path = Path(output_path_text).resolve()
    else:
        output_file_path = package_root / "节点图" / graph_scope / f"自动解析_节点图_{int(graph_id_int)}.py"

    _write_text(output_file_path, code_text)

    print("=" * 80)
    print("Graph Code 生成完成：")
    print(f"- package_root: {package_root}")
    print(f"- graph_id_int: {graph_id_int}")
    print(f"- output: {output_file_path}")
    print(f"- nodes: {len(graph_model.nodes)}")
    print(f"- edges: {len(graph_model.edges)}")
    print("=" * 80)

    if bool(args.validate):
        from engine.configs.settings import settings
        from engine.validate import validate_files

        settings.set_config_path(graph_generater_root.resolve())
        report = validate_files([output_file_path], workspace=graph_generater_root.resolve())
        error_issues = [issue for issue in report.issues if issue.level == "error"]
        warning_issues = [issue for issue in report.issues if issue.level == "warning"]

        print("Graph Code 校验完成（单文件）：")
        print(f"- file: {output_file_path}")
        print(f"- errors: {len(error_issues)}")
        print(f"- warnings: {len(warning_issues)}")
        if len(error_issues) > 0:
            raise SystemExit(1)

    if bool(args.diff):
        from engine.graph.graph_code_parser import GraphCodeParser

        parser = GraphCodeParser(graph_generater_root.resolve(), verbose=False, strict=True)
        parsed_model, _parsed_meta = parser.parse_file(output_file_path)

        diff = _diff_graph_models_by_titles_and_ports(src_graph=graph_model, gen_graph=parsed_model)
        nodes_only_in_src = diff["nodes_only_in_src"]
        nodes_only_in_gen = diff["nodes_only_in_generated"]
        edges_only_in_src = diff["edges_only_in_src"]
        edges_only_in_gen = diff["edges_only_in_generated"]

        print("=" * 80)
        print("Round-trip Diff（pyugc GraphModel vs 生成代码解析 GraphModel）：")
        print(f"- nodes_only_in_src: {sum(nodes_only_in_src.values())}")
        print(f"- nodes_only_in_generated: {sum(nodes_only_in_gen.values())}")
        print(f"- edges_only_in_src: {sum(edges_only_in_src.values())}")
        print(f"- edges_only_in_generated: {sum(edges_only_in_gen.values())}")

        def _print_counter(title: str, counter_obj: Any, limit: int = 20) -> None:
            items = list(counter_obj.items())
            if not items:
                return
            items.sort(key=lambda kv: (-int(kv[1]), str(kv[0])))
            print(title)
            for k, v in items[: int(limit)]:
                print(f"  - {k}: {v}")

        _print_counter("Nodes only in src:", nodes_only_in_src)
        _print_counter("Nodes only in generated:", nodes_only_in_gen)
        _print_counter("Edges only in src:", edges_only_in_src)
        _print_counter("Edges only in generated:", edges_only_in_gen)
        print("=" * 80)


if __name__ == "__main__":
    main()

