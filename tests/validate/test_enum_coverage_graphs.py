from __future__ import annotations

import ast
from pathlib import Path

from engine.validate.rules.node_index import callable_node_defs_by_name


def _collect_string_literals(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(getattr(node, "value", None), str):
            values.add(str(node.value))
    return values


def _expected_enum_literals(workspace_path: Path, *, scope: str) -> set[str]:
    node_defs = callable_node_defs_by_name(workspace_path, scope, include_composite=True)
    expected: set[str] = set()
    for _, node_def in node_defs.items():
        input_enum_options = dict(getattr(node_def, "input_enum_options", {}) or {})
        output_enum_options = dict(getattr(node_def, "output_enum_options", {}) or {})
        if not input_enum_options and not output_enum_options:
            continue
        for options in input_enum_options.values():
            expected.update(str(x) for x in (options or []) if isinstance(x, str) and x)
        for options in output_enum_options.values():
            expected.update(str(x) for x in (options or []) if isinstance(x, str) and x)
    return expected


def test_enum_coverage_graphs_include_all_enum_literals():
    """确保枚举覆盖图中包含节点库声明的全部枚举候选文本（server/client 分开统计）。"""
    workspace_path = Path(__file__).resolve().parents[2]

    server_graph_dir = (
        workspace_path / "assets/资源库/项目存档/test_enum_coverage/节点图/server/实体节点图/校准_枚举覆盖_v1"
    )
    client_graph_dir = (
        workspace_path / "assets/资源库/项目存档/test_enum_coverage/节点图/client/技能节点图/校准_枚举覆盖_v1"
    )

    server_graph_paths = sorted(server_graph_dir.glob("*.py"))
    client_graph_paths = sorted(client_graph_dir.glob("*.py"))

    assert server_graph_paths, f"missing enum coverage graphs in: {server_graph_dir}"
    assert client_graph_paths, f"missing enum coverage graphs in: {client_graph_dir}"

    for p in server_graph_paths + client_graph_paths:
        assert p.is_file(), f"missing graph file: {p}"

    expected_server = _expected_enum_literals(workspace_path, scope="server")
    expected_client = _expected_enum_literals(workspace_path, scope="client")

    actual_server: set[str] = set()
    for p in server_graph_paths:
        actual_server |= _collect_string_literals(p)

    actual_client: set[str] = set()
    for p in client_graph_paths:
        actual_client |= _collect_string_literals(p)

    missing_server = sorted(expected_server - actual_server)
    missing_client = sorted(expected_client - actual_client)

    assert not missing_server, f"server enum literals missing in coverage graphs: {missing_server[:50]}"
    assert not missing_client, f"client enum literals missing in coverage graphs: {missing_client[:50]}"


