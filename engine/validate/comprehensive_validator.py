"""综合验证器入口，负责调度各领域规则与图结构检查。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TYPE_CHECKING

from engine.graph.models.graph_model import GraphModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.resources.resource_manager import ResourceManager

from .comprehensive_graph_checks import (
    validate_graph,
    validate_graph_port_definitions,
    validate_graph_structure,
    validate_graph_structure_only,
    validate_graph_unified,
    validate_node_mount_and_scope,
)
from .comprehensive_rules import build_rules
from .comprehensive_rules.helpers import clear_graph_snapshot_cache
from .comprehensive_types import ValidationIssue
from .context import ValidationContext
from .pipeline import ValidationPipeline
from .rules.node_index import clear_node_index_caches

if TYPE_CHECKING:
    from engine.resources.package_interfaces import PackageLike


class ComprehensiveValidator:
    """存档级综合验证器。

    说明：
        - `package` 接受任何实现了 `PackageLike` 协议的对象，例如 `PackageView`；
        - 仅依赖其公开的只读字段（templates/instances/level_entity/signals 等）进行校验。
    """

    def __init__(
        self,
        package: "PackageLike",
        resource_manager: ResourceManager | None = None,
        verbose: bool = False,
    ):
        self.package = package
        self.resource_manager = resource_manager
        self.verbose = verbose
        self.issues: List[ValidationIssue] = []
        self.node_library: Dict[str, NodeDef] = {}
        self.workspace_path: Path | None = None
        self._capture_stack: List[List[ValidationIssue]] = []
        if resource_manager and hasattr(resource_manager, "workspace_path"):
            registry = get_node_registry(
                resource_manager.workspace_path, include_composite=True
            )
            self.node_library = registry.get_library()
        self._rules: Optional[List[Any]] = None

    def _ensure_rules(self) -> List[Any]:
        if self._rules is None:
            self._rules = build_rules(self)
        return self._rules

    def report_issue(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if self._capture_stack:
            self._capture_stack[-1].append(issue)

    def report_issues(self, issues: Iterable[ValidationIssue]) -> None:
        for issue in issues:
            self.report_issue(issue)

    def _capture_issues(self, func, *args, **kwargs) -> List[ValidationIssue]:
        buffer: List[ValidationIssue] = []
        start_index = len(self.issues)
        self._capture_stack.append(buffer)
        try:
            func(*args, **kwargs)
        finally:
            self._capture_stack.pop()
        if buffer and len(buffer) == len(self.issues) - start_index:
            return buffer
        return self.issues[start_index:]

    def validate_all(self) -> List[ValidationIssue]:
        self.issues = []
        clear_node_index_caches()
        clear_graph_snapshot_cache()
        workspace_path = (
            self.resource_manager.workspace_path
            if self.resource_manager and hasattr(self.resource_manager, "workspace_path")
            else Path(".")
        )
        self.workspace_path = workspace_path
        ctx = ValidationContext(
            workspace_path=workspace_path,
            package=self.package,
            resource_manager=self.resource_manager,
            node_library=self.node_library,
            verbose=self.verbose,
        )
        pipeline = ValidationPipeline(rules=self._ensure_rules())
        self.issues = pipeline.run(ctx)
        return self.issues

    def validate_graph_for_ui(
        self,
        graph_model: GraphModel,
        entity_type: str,
        location: str,
        detail: Dict[str, Any],
    ) -> List[ValidationIssue]:
        self.issues = []
        clear_graph_snapshot_cache()
        if not graph_model:
            return self.issues
        graph_data = graph_model.serialize()
        if not graph_data or "nodes" not in graph_data:
            return self.issues
        collected = self.validate_graph_data(
            graph_data,
            entity_type,
            location,
            detail,
            graph_model=graph_model,
        )
        return collected

    def get_summary(self) -> Dict[str, Any]:
        error_count = sum(1 for i in self.issues if i.level == "error")
        warning_count = sum(1 for i in self.issues if i.level == "warning")
        info_count = sum(1 for i in self.issues if i.level == "info")
        return {
            "total_issues": len(self.issues),
            "errors": error_count,
            "warnings": warning_count,
            "infos": info_count,
            "passed": error_count == 0,
        }

    def get_issues_by_category(self) -> Dict[str, List[ValidationIssue]]:
        categorized: Dict[str, List[ValidationIssue]] = {}
        for issue in self.issues:
            categorized.setdefault(issue.category, []).append(issue)
        return categorized

    def generate_report(self, format_type: str = "text") -> str:
        if format_type == "json":
            import json

            return json.dumps(
                {
                    "package_id": self.package.package_id,
                    "package_name": self.package.name,
                    "summary": self.get_summary(),
                    "issues": [
                        {
                            "level": issue.level,
                            "category": issue.category,
                            "location": issue.location,
                            "message": issue.message,
                            "suggestion": issue.suggestion,
                            "reference": issue.reference,
                        }
                        for issue in self.issues
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )

        lines = [
            "=" * 70,
            f"存档验证报告: {self.package.name}",
            f"存档ID: {self.package.package_id}",
            "=" * 70,
            "",
        ]
        summary = self.get_summary()
        if summary["passed"]:
            lines.append("✅ 所有验证通过！")
        else:
            lines.append(f"发现 {summary['total_issues']} 个问题:")
            if summary["errors"]:
                lines.append(f"  ❌ {summary['errors']} 个错误")
            if summary["warnings"]:
                lines.append(f"  ⚠️ {summary['warnings']} 个警告")
            if summary["infos"]:
                lines.append(f"  ℹ️ {summary['infos']} 个提示")
        lines.append("")
        lines.append("-" * 70)
        for category, issues in self.get_issues_by_category().items():
            lines.append(f"\n【{category}】 ({len(issues)} 个问题)")
            for issue in issues:
                lines.append("")
                lines.append(str(issue))
        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    # === Graph helper wrappers ===
    def validate_graph_data(
        self,
        graph_data: Dict,
        entity_type: str,
        location: str,
        detail: Dict,
        graph_model: GraphModel | None = None,
    ) -> List[ValidationIssue]:
        return self._capture_issues(
            validate_graph,
            self,
            graph_data,
            entity_type,
            location,
            detail,
            graph_model,
        )

    def validate_graph_run_only(
        self,
        graph_data: Dict,
        location: str,
        detail: Dict,
        virtual_pin_mappings: Optional[Dict] = None,
    ) -> List[ValidationIssue]:
        return self._capture_issues(
            validate_graph_unified,
            self,
            graph_data,
            location,
            detail,
            virtual_pin_mappings,
        )

    def validate_graph_structure_only_checks(
        self,
        graph_data: Dict,
        location: str,
        detail: Dict,
    ) -> List[ValidationIssue]:
        return self._capture_issues(
            validate_graph_structure_only,
            self,
            graph_data,
            location,
            detail,
        )


__all__ = ["ComprehensiveValidator", "ValidationIssue"]

