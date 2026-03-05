from __future__ import annotations

from typing import List

from engine.resources.resource_manager import ResourceManager, ResourceType

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


class ResourceLibraryGraphsRule(BaseComprehensiveRule):
    rule_id = "package.resource_graphs"
    category = "资源库节点图"
    # 注意：存档级综合校验不应承担“节点图源码/图结构”的严格校验职责；
    # 节点图结构与代码质量请使用 app-cli 的 validate-graphs/validate-file（或 release 的 Tools.exe）。
    default_level = "warning"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_resource_library_graphs(self.validator)


def validate_resource_library_graphs(validator) -> List[ValidationIssue]:
    resource_manager: ResourceManager | None = validator.resource_manager
    if not resource_manager:
        return []
    graph_ids = resource_manager.list_resources(ResourceType.GRAPH)
    if not graph_ids:
        return []
    issues: List[ValidationIssue] = []
    for graph_id in graph_ids:
        # 仅检查节点图“元数据可读/文件存在”，避免触发严格解析导致存档级校验被节点图错误阻断。
        metadata = resource_manager.load_graph_metadata(graph_id)
        if not isinstance(metadata, dict):
            issues.append(
                ValidationIssue(
                    level="error",
                    category=ResourceLibraryGraphsRule.category,
                    code="RESOURCE_GRAPH_METADATA_MISSING",
                    message="节点图元数据不可读取或文件缺失。",
                    location=f"资源库节点图 ({graph_id})",
                    suggestion=(
                        "请使用：Ayaya_Miliastra_Editor_Tools.exe validate-file <图文件路径> "
                        "（或源码环境：python -X utf8 -m app.cli.graph_tools validate-file <图文件路径>）"
                        "进行定位与修复。"
                    ),
                    detail={"type": "resource_graph_metadata", "graph_id": graph_id},
                )
            )
            continue

        graph_name_value = metadata.get("name")
        graph_name = graph_name_value.strip() if isinstance(graph_name_value, str) else ""
        if not graph_name:
            graph_name = graph_id

        file_graph_id_value = metadata.get("graph_id")
        file_graph_id = file_graph_id_value.strip() if isinstance(file_graph_id_value, str) else ""
        if file_graph_id and file_graph_id != graph_id:
            issues.append(
                ValidationIssue(
                    level="warning",
                    category=ResourceLibraryGraphsRule.category,
                    code="RESOURCE_GRAPH_ID_MISMATCH",
                    message=f"节点图文件内声明的 graph_id 与索引 ID 不一致：file={file_graph_id!r} index={graph_id!r}。",
                    location=f"资源库节点图 '{graph_name}' ({graph_id})",
                    suggestion="建议统一 graph_id，避免引用与文件定位产生歧义。",
                    detail={
                        "type": "resource_graph_metadata",
                        "graph_id": graph_id,
                        "graph_name": graph_name,
                        "file_graph_id": file_graph_id,
                    },
                )
            )
    return issues


__all__ = ["ResourceLibraryGraphsRule"]

