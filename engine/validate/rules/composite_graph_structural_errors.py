from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.graph import deserialize_graph, validate_graph_model
from engine.graph.composite_code_parser import CompositeCodeParser
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry

from ..comprehensive_graph_checks import describe_graph_error
from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule


def _get_or_parse_composite_config(
    ctx: ValidationContext,
    *,
    node_library: Dict[str, NodeDef],
) -> Any:
    cached = getattr(ctx, "composite_config", None)
    if cached is not None:
        return cached
    if ctx.file_path is None:
        return None
    parser = CompositeCodeParser(
        node_library=node_library,
        verbose=False,
        workspace_path=ctx.workspace_path,
    )
    composite = parser.parse_file(ctx.file_path)
    ctx.composite_config = composite
    return composite


def _virtual_pin_mappings_from_composite(composite: object) -> Dict[Tuple[str, str], bool]:
    mappings: Dict[Tuple[str, str], bool] = {}
    virtual_pins = list(getattr(composite, "virtual_pins", []) or [])
    for vpin in virtual_pins:
        for mapped in list(getattr(vpin, "mapped_ports", []) or []):
            node_id = str(getattr(mapped, "node_id", "") or "").strip()
            port_name = str(getattr(mapped, "port_name", "") or "").strip()
            if not node_id or not port_name:
                continue
            mappings[(node_id, port_name)] = bool(getattr(mapped, "is_input", False))
    return mappings


class CompositeGraphStructuralErrorsRule(ValidationRule):
    """复合节点：对子图执行 validate_graph_model（对齐 UI 严格加载），避免“校验通过但 UI 报错”。"""

    rule_id = "engine_composite_graph_structural_errors"
    category = "复合节点结构"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if (not ctx.is_composite) or ctx.file_path is None:
            return []

        node_library = getattr(ctx, "node_library", None)
        if not isinstance(node_library, dict) or not node_library:
            registry = get_node_registry(ctx.workspace_path, include_composite=True)
            node_library = registry.get_library()
            ctx.node_library = node_library

        composite = _get_or_parse_composite_config(ctx, node_library=dict(node_library))
        if composite is None:
            return []

        composite_id = str(getattr(composite, "composite_id", "") or "").strip()
        node_name = str(getattr(composite, "node_name", "") or "").strip()
        sub_graph = getattr(composite, "sub_graph", None)
        if not isinstance(sub_graph, dict):
            return []

        model = deserialize_graph(sub_graph)
        virtual_pin_mappings = _virtual_pin_mappings_from_composite(composite)
        errors = validate_graph_model(
            model,
            virtual_pin_mappings,
            workspace_path=ctx.workspace_path,
            node_library=dict(node_library),
        )
        if not errors:
            return []

        file_path = str(Path(ctx.file_path).resolve())
        issues: List[EngineIssue] = []
        for error_text in errors:
            category, suggestion, code = describe_graph_error(str(error_text or ""))
            message = str(error_text or "").strip()
            if suggestion:
                message = f"{message}\n建议：{suggestion}"
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=category or self.category,
                    code=code or "COMPOSITE_CONNECTION_STRUCTURE",
                    message=message,
                    file=file_path,
                    detail={
                        "composite_id": composite_id,
                        "node_name": node_name,
                    },
                )
            )
        return issues


__all__ = [
    "CompositeGraphStructuralErrorsRule",
]

