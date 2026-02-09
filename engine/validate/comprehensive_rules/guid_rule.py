from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple

from engine.resources.package_guid_index import (
    GuidCollision,
    ResourceRef,
    iter_package_guid_candidates,
    build_package_guid_index,
)
from engine.validate.id_digits import is_digits_1_to_10

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


_SPECIAL_VIEW_PACKAGE_IDS: Set[str] = {"global_view"}


def _group_guid_collisions(collisions: Sequence[GuidCollision]) -> Dict[str, List[GuidCollision]]:
    grouped: Dict[str, List[GuidCollision]] = {}
    for collision in collisions:
        grouped.setdefault(collision.guid, []).append(collision)
    return grouped


def _collect_unique_collision_targets(
    collisions: Sequence[GuidCollision],
) -> List[Tuple[ResourceRef, str]]:
    results: List[Tuple[ResourceRef, str]] = []
    seen: Set[Tuple[str, str]] = set()

    for collision in collisions:
        first_key = (collision.first.resource_type.name, collision.first.resource_id)
        if first_key not in seen:
            results.append((collision.first, collision.first_name))
            seen.add(first_key)

        second_key = (collision.second.resource_type.name, collision.second.resource_id)
        if second_key not in seen:
            results.append((collision.second, collision.second_name))
            seen.add(second_key)

    return results


class PackageGuidUniquenessRule(BaseComprehensiveRule):
    """包内 GUID 唯一性校验（跨模板/实体摆放/关卡实体）。"""

    rule_id = "package.guid_uniqueness"
    category = "资源系统"
    default_level = "error"

    def run(self, validation_context) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        issues.extend(validate_package_guid_format(self.validator))
        issues.extend(validate_package_guid_uniqueness(self.validator))
        return issues


def validate_package_guid_uniqueness(validator) -> List[ValidationIssue]:
    package = getattr(validator, "package", None)
    resource_manager = getattr(validator, "resource_manager", None)
    if package is None or resource_manager is None:
        return []

    package_id_value = getattr(package, "package_id", "")
    package_id = str(package_id_value or "").strip()
    if not package_id or package_id in _SPECIAL_VIEW_PACKAGE_IDS:
        return []

    package_name = str(getattr(package, "name", "") or "").strip() or package_id
    package_index = getattr(package, "package_index", None)
    if package_index is None:
        return []

    index = build_package_guid_index(
        package_id,
        package_index,
        resource_manager=resource_manager,
    )

    issues: List[ValidationIssue] = []
    base_location = f"存档 '{package_name}' ({package_id}) > GUID 解析"

    # 1) 包内引用的资源不存在：无法参与 GUID 索引构建
    for resource_ref in index.missing_resources:
        issues.append(
            ValidationIssue(
                level="error",
                category="资源系统",
                location=base_location,
                message=(
                    "存档索引引用了不存在的资源，无法构建包内 GUID 索引："
                    f"{resource_ref.resource_type.value}:{resource_ref.resource_id}"
                ),
                suggestion=(
                    "请在资源库中创建该资源，或从存档索引（PackageIndex）中移除该引用。"
                    "（templates/instances/level_entity_id 均会参与 GUID 索引）"
                ),
                reference="资源系统_统一解析层与GUID作用域.md: Phase 4.1",
                detail={
                    "type": "package_guid_missing_resource",
                    "package_id": package_id,
                    "resource_type": resource_ref.resource_type.value,
                    "resource_id": resource_ref.resource_id,
                },
            )
        )

    # 2) 包内 GUID 重复：必须在校验阶段报错（禁止静默取第一条）
    collisions_by_guid = _group_guid_collisions(index.collisions)
    for guid, collisions in collisions_by_guid.items():
        targets = _collect_unique_collision_targets(collisions)
        formatted_targets = ", ".join(
            f"{ref.resource_type.value}:{ref.resource_id}({display_name})"
            for ref, display_name in targets
        )

        issues.append(
            ValidationIssue(
                level="error",
                category="资源系统",
                location=base_location,
                message=f"GUID 在同一项目存档内出现重复，必须唯一：{guid}",
                suggestion=(
                    "请确保同一项目存档内同 GUID 只对应一个对象；"
                    "如需保留多个对象，请修改其中一个资源的 metadata.guid。"
                ),
                reference="资源系统_统一解析层与GUID作用域.md: Phase 4.1",
                detail={
                    "type": "package_guid_collision",
                    "package_id": package_id,
                    "guid": guid,
                    "targets": formatted_targets,
                },
            )
        )

    return issues


def validate_package_guid_format(validator) -> List[ValidationIssue]:
    """校验资源 metadata.guid 的格式：必须为 1~10 位纯数字。

    说明：
    - GUID 在引擎内就是数字 ID（可用字符串包裹数字）形式的标识；因此统一要求纯数字形态。
    - 该规则只检查“资源元数据中的 guid 字段”，不对信号/结构体等其他 ID 字段做推断。
    """
    package = getattr(validator, "package", None)
    resource_manager = getattr(validator, "resource_manager", None)
    if package is None or resource_manager is None:
        return []

    package_id_value = getattr(package, "package_id", "")
    package_id = str(package_id_value or "").strip()
    if not package_id or package_id in _SPECIAL_VIEW_PACKAGE_IDS:
        return []

    package_name = str(getattr(package, "name", "") or "").strip() or package_id
    package_index = getattr(package, "package_index", None)
    if package_index is None:
        return []

    base_location = f"存档 '{package_name}' ({package_id}) > GUID 格式"
    issues: List[ValidationIssue] = []

    def _normalize_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    for resource_ref in iter_package_guid_candidates(package_index):
        metadata = resource_manager.get_resource_metadata(
            resource_ref.resource_type, resource_ref.resource_id
        )
        if not isinstance(metadata, dict):
            continue

        guid_text = _normalize_text(metadata.get("guid"))
        if not guid_text:
            continue

        if is_digits_1_to_10(guid_text):
            continue

        display_name = _normalize_text(metadata.get("name")) or resource_ref.resource_id
        location = (
            f"{base_location} > {resource_ref.resource_type.value}:{resource_ref.resource_id}({display_name})"
        )
        issues.append(
            ValidationIssue(
                level="error",
                category="资源系统",
                code="RESOURCE_GUID_DIGITS_1_TO_10_REQUIRED",
                location=location,
                message=(
                    "资源 metadata.guid 必须为 1~10 位纯数字（允许用字符串包裹数字）；"
                    f"当前为 '{guid_text}'"
                ),
                suggestion="请将 metadata.guid 修改为 0~9999999999 的数字（或对应的数字字符串），并确保同一项目存档内唯一。",
                reference="资源系统_统一解析层与GUID作用域.md: Phase 4.1",
                detail={
                    "type": "package_guid_format_invalid",
                    "package_id": package_id,
                    "resource_type": resource_ref.resource_type.value,
                    "resource_id": resource_ref.resource_id,
                    "resource_name": display_name,
                    "guid": guid_text,
                },
            )
        )

    return issues


__all__ = [
    "PackageGuidUniquenessRule",
    "validate_package_guid_uniqueness",
    "validate_package_guid_format",
]


