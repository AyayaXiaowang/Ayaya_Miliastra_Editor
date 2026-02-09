from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from engine.graph import deserialize_graph
from engine.graph import validate_graph_model
from engine.graph.composite_code_parser import CompositeCodeParser
from engine.nodes.composite_file_policy import is_composite_definition_file
from engine.nodes.node_registry import get_node_registry

from .comprehensive_graph_checks import describe_graph_error
from .graph_validation_targets import relative_path_for_display
from .issue import EngineIssue

def collect_composite_structural_issues(
    targets: Sequence[Path],
    workspace: Path,
) -> List[EngineIssue]:
    """对复合节点补齐“图结构校验”，覆盖 UI 报的“缺少数据来源/未连接”等问题。

    设计边界：
    - 仅对复合节点定义文件（由引擎 `engine.nodes.composite_file_policy` 判定）执行；
    - 规则复用底层 `engine.graph.validate_graph_model`，并使用 `describe_graph_error` 统一映射分类/建议/错误码；
    - 返回 `EngineIssue` 列表，不做任何输出。
    """
    workspace_path = Path(workspace)
    registry = get_node_registry(workspace_path, include_composite=True)
    node_library = registry.get_library()
    parser = CompositeCodeParser(node_library, verbose=False, workspace_path=workspace_path)

    issues: List[EngineIssue] = []
    for file_path in targets:
        if not is_composite_definition_file(file_path):
            continue
        if not file_path.is_file():
            continue

        composite = parser.parse_file(file_path)
        model = deserialize_graph(composite.sub_graph)

        virtual_pin_mappings: Dict[Tuple[str, str], bool] = {}
        for vpin in composite.virtual_pins:
            for mapped in vpin.mapped_ports:
                virtual_pin_mappings[(str(mapped.node_id), str(mapped.port_name))] = bool(
                    mapped.is_input
                )

        errors = validate_graph_model(
            model,
            virtual_pin_mappings,
            workspace_path=workspace_path,
            node_library=node_library,
        )
        if not errors:
            continue

        relative_text = relative_path_for_display(file_path, workspace_path)
        base_detail = {
            "type": "composite_node",
            "composite_id": str(getattr(composite, "composite_id", "") or ""),
            "node_name": str(getattr(composite, "node_name", "") or ""),
        }
        for error in errors:
            category, suggestion, code = describe_graph_error(error)
            message = error if not suggestion else f"{error}\n建议：{suggestion}"
            issues.append(
                EngineIssue(
                    level="error",
                    category=category,
                    code=code,
                    message=message,
                    file=relative_text,
                    detail=dict(base_detail),
                )
            )
    return issues


__all__ = ["collect_composite_structural_issues"]


