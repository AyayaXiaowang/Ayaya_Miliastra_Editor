from __future__ import annotations

from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from engine.nodes.node_definition_loader import load_all_nodes
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.validate.node_graph_validator import validate_file
from tests._helpers.project_paths import get_repo_root


def _load_workspace_root() -> Path:
    return get_repo_root()


def _load_workspace_node_library() -> dict:
    workspace_root = _load_workspace_root()
    return load_all_nodes(workspace_root, include_composite=True, verbose=False)


def test_validate_passed_but_no_isolated_data_copies_should_exist() -> None:
    """校验通过后，布局阶段不应生成“无任何数据链引用”的跨块数据副本。

    该类节点在 UI 中会表现为：
    - 未找到关联链路：该节点未被任何数据链引用
    - 且通常带有 `*_copy_block_*` 后缀（is_data_node_copy=True）
    """

    workspace_root = _load_workspace_root()
    graph_path = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "测试"
        / "测试_复杂控制流综合测试.py"
    )
    assert graph_path.is_file()

    passed, errors, _warnings = validate_file(graph_path)
    assert passed, "\n".join(errors)

    node_library = _load_workspace_node_library()
    parser = GraphCodeParser(workspace_root, node_library=node_library, verbose=False)
    model, _ = parser.parse_file(graph_path)

    outgoing_by_src: dict[str, list] = {}
    for edge in model.edges.values():
        outgoing_by_src.setdefault(edge.src_node, []).append(edge)

    offenders: list[str] = []
    for node in model.nodes.values():
        if not bool(getattr(node, "is_data_node_copy", False)):
            continue
        outgoing_edges = outgoing_by_src.get(node.id, []) or []
        outgoing_data_edges = [
            edge for edge in outgoing_edges if not is_flow_port_name(edge.src_port)
        ]
        if outgoing_data_edges:
            continue
        original_node_id = str(getattr(node, "original_node_id", "") or "")
        copy_block_id = str(getattr(node, "copy_block_id", "") or "")
        offenders.append(
            f"{node.id} (title={node.title}, original={original_node_id}, copy_block={copy_block_id}, line={node.source_lineno})"
        )

    assert offenders == [], "发现无数据输出引用的跨块数据副本:\n" + "\n".join(offenders)


