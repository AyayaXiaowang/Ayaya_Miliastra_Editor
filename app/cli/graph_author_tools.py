from __future__ import annotations

"""
Graph authoring tools (CLI).

This module provides developer-facing helpers to improve the *writing experience*:
- Generate richer `.pyi` stubs for node functions (better keyword autocomplete, port type hints).
- Insert/update a `GV` constants block to reduce variable-name string typos.

Run (PowerShell: no `&&`, execute line by line):
  python -X utf8 -m app.cli.graph_author_tools --help
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Sequence


if not __package__ and not getattr(sys, "frozen", False):
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.graph_author_tools --help\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )


from engine.utils.workspace import resolve_workspace_root, init_settings_for_workspace  # noqa: E402
from engine.utils.source_text import read_text  # noqa: E402

from engine.graph.utils.authoring_tools import (  # noqa: E402
    find_graph_variables_decl_span,
    normalize_graph_variables,
    upsert_graph_var_name_constants_block,
)
from engine.graph.utils.metadata_extractor import extract_graph_variables_from_ast  # noqa: E402
from engine.nodes.stubgen import generate_nodes_pyi_stub  # noqa: E402


def _parse_cli(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="graph_author_tools",
        description="Graph Code 写作辅助工具（stubs / 变量名常量）",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        dest="workspace_root",
        default="",
        help="工作区根目录（默认：源码=仓库根目录；冻结=exe 所在目录）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_stubs = subparsers.add_parser(
        "generate-node-stubs",
        help="生成/刷新节点函数类型桩（plugins/nodes/{server,client}/__init__.pyi）",
    )
    gen_stubs.add_argument(
        "--scope",
        choices=["server", "client", "all"],
        default="all",
        help="生成范围（默认 all）",
    )

    sync_vars = subparsers.add_parser(
        "sync-graph-vars",
        help="生成/刷新 GV 变量名常量块（基于 GRAPH_VARIABLES）",
    )
    sync_vars.add_argument(
        "file",
        help="节点图文件路径（可相对 workspace_root）",
    )
    sync_vars.add_argument(
        "--class-name",
        default="GV",
        help="变量名常量类名（默认 GV）",
    )
    sync_vars.add_argument(
        "--no-gv",
        action="store_true",
        help="不插入/更新 GV 变量名常量块",
    )

    return parser.parse_args(list(argv))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _run_generate_node_stubs(workspace_root: Path, scope: str) -> int:
    targets: list[tuple[str, Path]] = []
    if scope in {"server", "all"}:
        targets.append(("server", workspace_root / "plugins" / "nodes" / "server" / "__init__.pyi"))
    if scope in {"client", "all"}:
        targets.append(("client", workspace_root / "plugins" / "nodes" / "client" / "__init__.pyi"))

    for s, path in targets:
        text = generate_nodes_pyi_stub(workspace_root, scope=s)
        _write_text(path, text)
        print(f"[ok] wrote: {path}")

    return 0


def _run_sync_graph_vars(workspace_root: Path, file_arg: str, *, class_name: str, no_gv: bool) -> int:
    raw_path = Path(file_arg)
    target_path = raw_path if raw_path.is_absolute() else (workspace_root / raw_path)
    target_path = target_path.resolve()
    if not target_path.is_file():
        raise FileNotFoundError(str(target_path))

    source_text = read_text(target_path)
    tree = ast.parse(source_text, filename=str(target_path))

    raw_vars = extract_graph_variables_from_ast(tree)
    graph_vars = normalize_graph_variables(raw_vars)

    new_text = source_text

    if not no_gv:
        span = find_graph_variables_decl_span(tree)
        insert_after = span[1] if span is not None else None
        new_text = upsert_graph_var_name_constants_block(
            new_text,
            graph_vars=graph_vars,
            insert_after_lineno=insert_after,
            class_name=class_name,
        )

    if new_text != source_text:
        _write_text(target_path, new_text)
        print(f"[ok] updated: {target_path}")
    else:
        print(f"[ok] no change: {target_path}")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parsed = _parse_cli(argv or sys.argv[1:])
    workspace_root = resolve_workspace_root(parsed.workspace_root)
    init_settings_for_workspace(workspace_root=workspace_root, load_user_settings=False)

    cmd = parsed.command
    if cmd == "generate-node-stubs":
        return _run_generate_node_stubs(workspace_root, str(parsed.scope))
    if cmd == "sync-graph-vars":
        return _run_sync_graph_vars(
            workspace_root,
            str(parsed.file),
            class_name=str(parsed.class_name),
            no_gv=bool(parsed.no_gv),
        )

    raise ValueError(f"unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main())


