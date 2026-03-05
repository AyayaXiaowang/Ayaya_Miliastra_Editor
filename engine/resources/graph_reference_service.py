"""节点图引用收集服务（单一真源）。

本模块负责回答两类问题：

1) 一个存档（package）引用了哪些 graph_id？
2) graph_id 被哪些资源（模板/实体摆放/关卡实体/战斗预设等）引用？

设计原则：
- 仅负责“引用关系”的抽取与归一化，不做图文件存在性校验，也不加载 GraphConfig；
- 允许不同调用方按需选择引用口径（例如是否包含战斗预设、是否包含 UGC 间接引用）；
- 不吞错：数据结构异常直接按 Python 规则抛出，便于尽早暴露资源问题。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from engine.configs.resource_types import ResourceType


@dataclass(frozen=True)
class GraphReference:
    """graph_id 的一次引用记录。"""

    reference_type: str  # template | instance | level_entity | combat_skill | combat_player_template | combat_player_class
    reference_id: str
    reference_name: str
    package_id: str
    graph_id: str
    source: str  # 规则来源/字段路径（用于调试与扩展）


def _normalize_graph_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _iter_graph_ids_from_list(values: object) -> Iterator[str]:
    if not isinstance(values, list) or not values:
        return
    for raw_value in values:
        graph_id = _normalize_graph_id(raw_value)
        if graph_id:
            yield graph_id


def _resolve_display_name(payload: Dict[str, Any], fallback_id: str, *, preferred_keys: Sequence[str]) -> str:
    for key in preferred_keys:
        raw_value = payload.get(key)
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if text:
                return text
    return fallback_id


def _extract_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata_value = payload.get("metadata")
    return metadata_value if isinstance(metadata_value, dict) else {}


def collect_graph_ids_from_resource_payload(
    resource_type: ResourceType,
    payload: Dict[str, Any],
    *,
    package_id: str = "",
    include_skill_ugc_indirect: bool = False,
) -> List[str]:
    """从单个资源 payload 中收集被引用的 graph_id 列表（去重，保持顺序稳定）。"""

    graph_ids: List[str] = []
    seen: set[str] = set()

    def append_graph_id(graph_id: str) -> None:
        if not graph_id:
            return
        if graph_id in seen:
            return
        seen.add(graph_id)
        graph_ids.append(graph_id)

    # 通用挂载点：default_graphs / additional_graphs
    for graph_id in _iter_graph_ids_from_list(payload.get("default_graphs")):
        append_graph_id(graph_id)
    for graph_id in _iter_graph_ids_from_list(payload.get("additional_graphs")):
        append_graph_id(graph_id)

    metadata = _extract_metadata(payload)

    # 玩家模板：metadata.player_editor.*.graphs
    if resource_type == ResourceType.PLAYER_TEMPLATE:
        player_editor = metadata.get("player_editor")
        if isinstance(player_editor, dict):
            for section_key in ("player", "role"):
                section = player_editor.get(section_key)
                if isinstance(section, dict):
                    for graph_id in _iter_graph_ids_from_list(section.get("graphs")):
                        append_graph_id(graph_id)
            roles_value = player_editor.get("roles")
            if isinstance(roles_value, list):
                for role_entry in roles_value:
                    if not isinstance(role_entry, dict):
                        continue
                    for graph_id in _iter_graph_ids_from_list(role_entry.get("graphs")):
                        append_graph_id(graph_id)

        return graph_ids

    # 职业：metadata.class_editor.graphs
    if resource_type == ResourceType.PLAYER_CLASS:
        class_editor = metadata.get("class_editor")
        if isinstance(class_editor, dict):
            for graph_id in _iter_graph_ids_from_list(class_editor.get("graphs")):
                append_graph_id(graph_id)
        return graph_ids

    # 技能：metadata.skill_editor.graphs（以及可选的 UGC 间接引用）
    if resource_type == ResourceType.SKILL:
        skill_editor = metadata.get("skill_editor")
        if isinstance(skill_editor, dict):
            for graph_id in _iter_graph_ids_from_list(skill_editor.get("graphs")):
                append_graph_id(graph_id)

        if include_skill_ugc_indirect:
            ugc = metadata.get("ugc")
            if isinstance(ugc, dict):
                referenced_graph_id_ints = ugc.get("referenced_graph_id_ints")
                if isinstance(referenced_graph_id_ints, list):
                    package_id_text = str(package_id or "").strip()
                    for graph_id_int_value in referenced_graph_id_ints:
                        if not isinstance(graph_id_int_value, int):
                            continue
                        graph_id_int = int(graph_id_int_value)
                        if graph_id_int <= 0:
                            continue
                        if package_id_text:
                            append_graph_id(f"client_graph_{graph_id_int}__{package_id_text}")
                            append_graph_id(f"server_graph_{graph_id_int}__{package_id_text}")

        return graph_ids

    return graph_ids


def iter_references_from_package_index(
    *,
    package_id: str,
    package_index: Any,
    resource_manager: Any,
    include_combat_presets: bool = True,
    include_skill_ugc_indirect: bool = False,
) -> Iterator[GraphReference]:
    """从 PackageIndex 派生出 graph 引用记录（需要 ResourceManager 读取资源 payload）。"""

    package_id_text = str(package_id or "").strip()
    if not package_id_text:
        return

    resources = getattr(package_index, "resources", None)
    if resources is None:
        return

    # --- 模板 default_graphs
    template_ids = list(getattr(resources, "templates", []) or [])
    for template_id_value in template_ids:
        template_id = _normalize_graph_id(template_id_value)
        if not template_id:
            continue
        template_payload = resource_manager.load_resource(ResourceType.TEMPLATE, template_id, copy_mode="none")
        if not isinstance(template_payload, dict):
            continue
        template_name = _resolve_display_name(template_payload, template_id, preferred_keys=("name",))
        for graph_id in _iter_graph_ids_from_list(template_payload.get("default_graphs")):
            yield GraphReference(
                reference_type="template",
                reference_id=template_id,
                reference_name=template_name,
                package_id=package_id_text,
                graph_id=graph_id,
                source="template.default_graphs",
            )

    # --- 实体摆放 additional_graphs
    instance_ids = list(getattr(resources, "instances", []) or [])
    for instance_id_value in instance_ids:
        instance_id = _normalize_graph_id(instance_id_value)
        if not instance_id:
            continue
        instance_payload = resource_manager.load_resource(ResourceType.INSTANCE, instance_id, copy_mode="none")
        if not isinstance(instance_payload, dict):
            continue
        instance_name = _resolve_display_name(instance_payload, instance_id, preferred_keys=("name",))
        for graph_id in _iter_graph_ids_from_list(instance_payload.get("additional_graphs")):
            yield GraphReference(
                reference_type="instance",
                reference_id=instance_id,
                reference_name=instance_name,
                package_id=package_id_text,
                graph_id=graph_id,
                source="instance.additional_graphs",
            )

    # --- 关卡实体 additional_graphs（以 PackageIndex.level_entity_id 指向的实例为准）
    level_entity_id_value = getattr(package_index, "level_entity_id", None)
    level_entity_id = _normalize_graph_id(level_entity_id_value)
    if level_entity_id:
        level_entity_payload = resource_manager.load_resource(ResourceType.INSTANCE, level_entity_id, copy_mode="none")
        if isinstance(level_entity_payload, dict):
            for graph_id in _iter_graph_ids_from_list(level_entity_payload.get("additional_graphs")):
                yield GraphReference(
                    reference_type="level_entity",
                    reference_id=package_id_text,
                    reference_name="关卡实体",
                    package_id=package_id_text,
                    graph_id=graph_id,
                    source="level_entity.additional_graphs",
                )

    if not include_combat_presets:
        return

    combat_presets = getattr(resources, "combat_presets", None)
    if not isinstance(combat_presets, dict):
        return

    # --- 玩家模板（战斗预设/玩家模板）：metadata.player_editor.*.graphs
    player_template_ids = combat_presets.get("player_templates", [])
    if isinstance(player_template_ids, list) and player_template_ids:
        for player_template_id_value in player_template_ids:
            player_template_id = _normalize_graph_id(player_template_id_value)
            if not player_template_id:
                continue
            payload = resource_manager.load_resource(
                ResourceType.PLAYER_TEMPLATE,
                player_template_id,
                copy_mode="none",
            )
            if not isinstance(payload, dict):
                continue
            display_name = _resolve_display_name(payload, player_template_id, preferred_keys=("template_name", "name"))
            for graph_id in collect_graph_ids_from_resource_payload(
                ResourceType.PLAYER_TEMPLATE,
                payload,
                package_id=package_id_text,
            ):
                yield GraphReference(
                    reference_type="combat_player_template",
                    reference_id=player_template_id,
                    reference_name=display_name,
                    package_id=package_id_text,
                    graph_id=graph_id,
                    source="combat.player_templates.metadata.player_editor.*.graphs",
                )

    # --- 职业（战斗预设/职业）：metadata.class_editor.graphs
    player_class_ids = combat_presets.get("player_classes", [])
    if isinstance(player_class_ids, list) and player_class_ids:
        for class_id_value in player_class_ids:
            class_id = _normalize_graph_id(class_id_value)
            if not class_id:
                continue
            payload = resource_manager.load_resource(ResourceType.PLAYER_CLASS, class_id, copy_mode="none")
            if not isinstance(payload, dict):
                continue
            display_name = _resolve_display_name(payload, class_id, preferred_keys=("class_name", "name"))
            for graph_id in collect_graph_ids_from_resource_payload(
                ResourceType.PLAYER_CLASS,
                payload,
                package_id=package_id_text,
            ):
                yield GraphReference(
                    reference_type="combat_player_class",
                    reference_id=class_id,
                    reference_name=display_name,
                    package_id=package_id_text,
                    graph_id=graph_id,
                    source="combat.player_classes.metadata.class_editor.graphs",
                )

    # --- 技能（战斗预设/技能）：metadata.skill_editor.graphs
    skill_ids = combat_presets.get("skills", [])
    if isinstance(skill_ids, list) and skill_ids:
        for skill_id_value in skill_ids:
            skill_id = _normalize_graph_id(skill_id_value)
            if not skill_id:
                continue
            payload = resource_manager.load_resource(ResourceType.SKILL, skill_id, copy_mode="none")
            if not isinstance(payload, dict):
                continue
            display_name = _resolve_display_name(payload, skill_id, preferred_keys=("skill_name", "name"))
            for graph_id in collect_graph_ids_from_resource_payload(
                ResourceType.SKILL,
                payload,
                package_id=package_id_text,
                include_skill_ugc_indirect=include_skill_ugc_indirect,
            ):
                yield GraphReference(
                    reference_type="combat_skill",
                    reference_id=skill_id,
                    reference_name=display_name,
                    package_id=package_id_text,
                    graph_id=graph_id,
                    source="combat.skills.metadata.skill_editor.graphs",
                )


def iter_referenced_graph_ids_from_package_index(
    *,
    package_id: str,
    package_index: Any,
    resource_manager: Any,
    include_combat_presets: bool = True,
    include_skill_ugc_indirect: bool = False,
) -> Iterator[str]:
    """从 PackageIndex 派生出被引用的 graph_id（去重，保持首次出现顺序）。"""

    seen: set[str] = set()
    for ref in iter_references_from_package_index(
        package_id=package_id,
        package_index=package_index,
        resource_manager=resource_manager,
        include_combat_presets=include_combat_presets,
        include_skill_ugc_indirect=include_skill_ugc_indirect,
    ):
        if ref.graph_id in seen:
            continue
        seen.add(ref.graph_id)
        yield ref.graph_id


def build_graph_to_references_index(
    *,
    package_index_manager: Any,
    resource_manager: Any,
    include_combat_presets: bool = True,
    include_skill_ugc_indirect: bool = False,
    refresh_resource_names: bool = False,
) -> Dict[str, List[Tuple[str, str, str, str]]]:
    """构建 graph_id -> references 的反向索引。

    返回结构保持与 UI 现有表格控件兼容：
    - value 为 (entity_type, entity_id, entity_name, package_id) 四元组列表
    """

    graph_to_refs: Dict[str, List[Tuple[str, str, str, str]]] = {}
    packages = list(package_index_manager.list_packages() or [])
    for package_info in packages:
        package_id_value = package_info.get("package_id")
        package_id = str(package_id_value or "").strip()
        if not package_id:
            continue
        package_index = package_index_manager.load_package_index(
            package_id,
            refresh_resource_names=bool(refresh_resource_names),
        )
        if package_index is None:
            continue
        for ref in iter_references_from_package_index(
            package_id=package_id,
            package_index=package_index,
            resource_manager=resource_manager,
            include_combat_presets=include_combat_presets,
            include_skill_ugc_indirect=include_skill_ugc_indirect,
        ):
            graph_to_refs.setdefault(ref.graph_id, []).append(
                (ref.reference_type, ref.reference_id, ref.reference_name, ref.package_id)
            )
    return graph_to_refs


__all__ = [
    "GraphReference",
    "build_graph_to_references_index",
    "collect_graph_ids_from_resource_payload",
    "iter_referenced_graph_ids_from_package_index",
    "iter_references_from_package_index",
]


