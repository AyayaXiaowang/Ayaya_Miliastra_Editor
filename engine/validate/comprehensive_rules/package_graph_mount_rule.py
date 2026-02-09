from __future__ import annotations

from typing import Dict, List, Set

from engine.validate.context import ValidationContext

from engine.configs.resource_types import ResourceType
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir
from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import GraphAttachment, iter_all_package_graphs


class PackageGraphMountRule(BaseComprehensiveRule):
    """检查存档目录内的节点图与挂载关系是否一致（目录即存档）。

    目标：
    - 提醒：存档目录下存在但未被任何模板/实体摆放/关卡实体挂载的节点图；
    - 提醒：模板/实体摆放/关卡实体引用了不属于“共享/当前存档目录”的节点图（或节点图文件缺失）。
    """

    rule_id = "package.graph_mount"
    category = "节点图挂载"
    default_level = "warning"

    def run(self, ctx: ValidationContext) -> List[ValidationIssue]:
        return validate_package_graph_mount(self.validator, ctx)


def validate_package_graph_mount(
    validator,
    ctx: ValidationContext,
) -> List[ValidationIssue]:
    package = ctx.package
    resource_manager = ctx.resource_manager
    if not package or not resource_manager:
        return []

    package_id = getattr(package, "package_id", "")
    if not isinstance(package_id, str) or not package_id:
        return []
    if package_id == "global_view":
        return []

    templates = getattr(package, "templates", {}) or {}
    instances = getattr(package, "instances", {}) or {}
    level_entity = getattr(package, "level_entity", None)
    combat_presets = getattr(package, "combat_presets", None)

    attachments: List[GraphAttachment] = list(
        iter_all_package_graphs(resource_manager, templates, instances, level_entity, combat_presets)
    )

    attached_graph_ids: Set[str] = set()
    attachment_by_graph: Dict[str, GraphAttachment] = {}
    for attachment in attachments:
        attached_graph_ids.add(attachment.graph_id)
        if attachment.graph_id not in attachment_by_graph:
            attachment_by_graph[attachment.graph_id] = attachment

    # 补充：技能节点图挂载（CombatPresets.skills[*].metadata.skill_editor.graphs）
    # 说明：
    # - 技能节点图属于合法挂载点，但不在模板/实体摆放/关卡实体/玩家模板的 graph 列表中；
    # - 若不计入会产生大量“未挂载节点图”的误报，影响导出/解析状态判断。
    if combat_presets is not None:
        skills_map = getattr(combat_presets, "skills", {}) or {}
        if isinstance(skills_map, dict):
            for skill_id, skill_payload in skills_map.items():
                if not isinstance(skill_payload, dict):
                    continue
                metadata_object = skill_payload.get("metadata")
                if not isinstance(metadata_object, dict):
                    continue
                skill_editor_object = metadata_object.get("skill_editor")
                if not isinstance(skill_editor_object, dict):
                    continue
                graphs_value = skill_editor_object.get("graphs")
                if not isinstance(graphs_value, list):
                    continue
                for graph_id_value in graphs_value:
                    if not isinstance(graph_id_value, str):
                        continue
                    graph_id_text = graph_id_value.strip()
                    if graph_id_text == "":
                        continue
                    attached_graph_ids.add(graph_id_text)

                # 兼容：ugc 导出会在 metadata.ugc.referenced_graph_id_ints 中记录技能间接引用的节点图 ID（int）。
                # 这类 server graph 可能不会出现在 skill_editor.graphs 中，但仍属于“技能体系可达”的挂载闭包。
                ugc_object = metadata_object.get("ugc")
                if not isinstance(ugc_object, dict):
                    continue
                referenced_graph_id_ints = ugc_object.get("referenced_graph_id_ints")
                if not isinstance(referenced_graph_id_ints, list):
                    continue
                for graph_id_int_value in referenced_graph_id_ints:
                    if not isinstance(graph_id_int_value, int):
                        continue
                    graph_id_int = int(graph_id_int_value)
                    if graph_id_int <= 0:
                        continue
                    attached_graph_ids.add(f"client_graph_{graph_id_int}__{package_id}")
                    attached_graph_ids.add(f"server_graph_{graph_id_int}__{package_id}")

    # 目录即存档：以“节点图文件所在目录”判定归属。
    resource_library_dir = getattr(resource_manager, "resource_library_dir", None)
    if resource_library_dir is None:
        return []

    shared_root_dir = get_shared_root_dir(resource_library_dir)
    package_root_dir = get_packages_root_dir(resource_library_dir) / package_id

    graph_path_map: Dict[str, object] = dict(getattr(resource_manager, "resource_index", {}).get(ResourceType.GRAPH, {}))
    graph_ids_in_shared: Set[str] = set()
    graph_ids_in_package: Set[str] = set()

    shared_root_resolved = shared_root_dir.resolve()
    package_root_resolved = package_root_dir.resolve()

    for graph_id, file_path_obj in graph_path_map.items():
        file_path = file_path_obj
        if not hasattr(file_path, "resolve"):
            continue
        resolved = file_path.resolve()
        if shared_root_resolved in resolved.parents:
            graph_ids_in_shared.add(graph_id)
            continue
        if package_root_resolved in resolved.parents:
            graph_ids_in_package.add(graph_id)
            continue

    issues: List[ValidationIssue] = []

    # 1) 存档目录下存在但未挂载的节点图：仅一条简单提示（不输出额外建议）。
    for graph_id in sorted(graph_ids_in_package, key=lambda x: x.casefold()):
        if graph_id in attached_graph_ids:
            continue
        issues.append(
            ValidationIssue(
                level="warning",
                category="节点图挂载",
                location=f"存档 '{package.name}' ({package_id}) > 节点图",
                message=f"节点图 '{graph_id}' 未挂载到任何模板或实体摆放。",
                suggestion="",
                detail={
                    "type": "unmounted_graph",
                    "package_id": package_id,
                    "graph_id": graph_id,
                },
            )
        )

    # 2) 对挂载的节点图做归属校验：必须在“共享/当前存档目录”之一，且文件存在。
    allowed_graph_ids: Set[str] = set(graph_ids_in_shared) | set(graph_ids_in_package)
    for graph_id, attachment in attachment_by_graph.items():
        if graph_id in allowed_graph_ids:
            continue
        issues.append(
            ValidationIssue(
                level="warning",
                category="节点图挂载",
                location=attachment.location_full,
                message=f"挂载的节点图 '{graph_id}' 不属于当前存档目录或共享目录。",
                suggestion="请将该节点图文件移动到 `共享/节点图/` 或当前项目存档的 `节点图/` 目录，或修改挂载引用。",
                detail={
                    "type": "attached_graph_out_of_root",
                    "package_id": package_id,
                    "graph_id": graph_id,
                    "owner_kind": attachment.owner_kind,
                    "owner_id": attachment.owner_id,
                    "owner_name": attachment.owner_name,
                },
            )
        )

    return issues


__all__ = ["PackageGraphMountRule", "validate_package_graph_mount"]


