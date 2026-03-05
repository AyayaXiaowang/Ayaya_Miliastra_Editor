from __future__ import annotations

from typing import Dict, List, Set

from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


_SPECIAL_VIEW_PACKAGE_IDS: Set[str] = {"global_view"}


class LevelVariableReferenceRule(BaseComprehensiveRule):
    """校验存档索引（PackageIndex）中声明的关卡变量引用是否都能解析到代码级定义。"""

    rule_id = "package.level_variable_references"
    category = "管理配置"
    default_level = "error"

    def run(self, validation_context) -> List[ValidationIssue]:
        return validate_level_variable_references(self.validator)


def validate_level_variable_references(validator) -> List[ValidationIssue]:
    package = getattr(validator, "package", None)
    if package is None:
        return []

    package_id_value = getattr(package, "package_id", "")
    package_id = str(package_id_value or "").strip()
    if not package_id or package_id in _SPECIAL_VIEW_PACKAGE_IDS:
        return []

    package_name = str(getattr(package, "name", "") or "").strip() or package_id
    package_index = getattr(package, "package_index", None)
    if package_index is None:
        return []

    resources_value = getattr(package_index, "resources", None)
    management_value = getattr(resources_value, "management", {}) if resources_value is not None else {}
    management_mapping: Dict[str, object] = management_value if isinstance(management_value, dict) else {}

    referenced_variable_ids = management_mapping.get("level_variables", [])
    if not isinstance(referenced_variable_ids, list) or not referenced_variable_ids:
        return []

    schema_view = get_default_level_variable_schema_view()
    all_variable_files = schema_view.get_all_variable_files() or {}

    issues: List[ValidationIssue] = []
    base_location = f"存档 '{package_name}' ({package_id}) > 管理配置 > 关卡变量引用"

    seen_variable_ids: Set[str] = set()
    duplicated_variable_ids: Set[str] = set()

    for referenced_id_value in referenced_variable_ids:
        if not isinstance(referenced_id_value, str):
            continue
        referenced_id = referenced_id_value.strip()
        if not referenced_id:
            continue

        if referenced_id in seen_variable_ids:
            duplicated_variable_ids.add(referenced_id)
            continue
        seen_variable_ids.add(referenced_id)

        # 现行语义：记录 VARIABLE_FILE_ID（变量文件 ID）
        if referenced_id in all_variable_files:
            continue

        issues.append(
            ValidationIssue(
                level="error",
                category="管理配置",
                location=base_location,
                message=f"存档索引引用了不存在的关卡变量文件/变量：{referenced_id}",
                suggestion=(
                    "请在该项目存档的 管理配置/关卡变量 下创建对应的变量文件（VARIABLE_FILE_ID），"
                    "或从存档索引 resources.management.level_variables 中移除该引用。"
                ),
                reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                detail={
                    "type": "package_level_variable_missing",
                    "package_id": package_id,
                    "referenced_id": referenced_id,
                },
            )
        )

    if duplicated_variable_ids:
        issues.append(
            ValidationIssue(
                level="warning",
                category="管理配置",
                location=base_location,
                message=(
                    "存档索引 resources.management.level_variables 中存在重复的 variable_id："
                    + ", ".join(sorted(duplicated_variable_ids))
                ),
                suggestion="请移除重复条目，保证引用列表稳定且无歧义。",
                reference="资源系统_统一解析层与GUID作用域.md: Phase 2.2",
                detail={
                    "type": "package_level_variable_duplicates",
                    "package_id": package_id,
                    "variable_ids": sorted(duplicated_variable_ids),
                },
            )
        )

    return issues


__all__ = ["LevelVariableReferenceRule", "validate_level_variable_references"]


