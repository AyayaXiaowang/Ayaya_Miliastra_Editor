from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from engine.configs.resource_types import ResourceType
from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
from engine.struct import get_default_struct_repository

from .package_guid_index import (
    PackageGuidIndex,
    PackageGuidIndexService,
    ResourceRef,
    build_package_guid_index,
)


SPECIAL_GLOBAL_PACKAGE_IDS: Set[str] = {"global_view"}


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_expected_types(expected_types: Optional[Sequence[ResourceType]]) -> Set[ResourceType]:
    if not expected_types:
        return set()
    normalized: Set[ResourceType] = set()
    for entry in expected_types:
        if isinstance(entry, ResourceType):
            normalized.add(entry)
    return normalized


@dataclass(frozen=True)
class ScopedGuidMatch:
    """全局 GUID 搜索时的匹配结果：携带 package_id 的 scoped 引用。"""

    package_id: str
    ref: ResourceRef


class RefResolver:
    """统一解析门面（Resolver）。

    设计目标：
    - 调用侧只做“一次解引用”；引用错误在校验阶段暴露（调用侧不写判空分支）。
    - package 内 GUID 必须唯一；全局视图允许多条匹配但必须显式选择 package。
    """

    def __init__(
        self,
        *,
        resource_manager,
        package_index_manager,
        guid_index_service: PackageGuidIndexService | None = None,
    ) -> None:
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        self._guid_index_service = guid_index_service or PackageGuidIndexService(
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
        self._level_variable_schema_view = get_default_level_variable_schema_view()
        self._struct_repo = get_default_struct_repository()

    # ---------------------------------------------------------------------
    # GUID 解析
    # ---------------------------------------------------------------------

    def build_package_guid_index_snapshot(self, package_id: str, package_index) -> PackageGuidIndex:
        """基于“已在内存中的 PackageIndex”构建包内 GUID 派生索引快照。

        使用场景：
        - UI/编辑器侧需要列举当前项目存档内可选 GUID（包含未落盘的索引内存改动）；
        - 调用侧不应直接依赖 `package_guid_index.build_package_guid_index`，而是统一走 Resolver。
        """
        return build_package_guid_index(
            package_id,
            package_index,
            resource_manager=self._resource_manager,
        )

    @staticmethod
    def _collect_collision_refs(index: PackageGuidIndex, guid: str) -> List[Tuple[ResourceRef, str]]:
        results: List[Tuple[ResourceRef, str]] = []
        seen: Set[Tuple[ResourceType, str]] = set()
        for collision in index.collisions:
            if collision.guid != guid:
                continue

            first_key = (collision.first.resource_type, collision.first.resource_id)
            if first_key not in seen:
                results.append((collision.first, collision.first_name))
                seen.add(first_key)

            second_key = (collision.second.resource_type, collision.second.resource_id)
            if second_key not in seen:
                results.append((collision.second, collision.second_name))
                seen.add(second_key)

        return results

    def try_resolve_guid(
        self,
        package_id: str,
        guid: str,
        *,
        expected_types: Optional[Sequence[ResourceType]] = None,
    ) -> Tuple[Optional[ResourceRef], str]:
        package_id_text = _normalize_text(package_id)
        guid_text = _normalize_text(guid)
        expected_resource_types = _normalize_expected_types(expected_types)

        if not package_id_text:
            return None, "package_id 不能为空"
        if not guid_text:
            return None, "guid 不能为空"

        if package_id_text in SPECIAL_GLOBAL_PACKAGE_IDS:
            return None, "全局视图下请使用 resolve_guid_global(guid) 获取全部匹配后再选择 package"

        index = self._guid_index_service.get_index(package_id_text)
        if not index.package_index_found:
            return None, f"未找到项目存档索引：{package_id_text}"

        collision_refs = self._collect_collision_refs(index, guid_text)
        if collision_refs:
            formatted = ", ".join(
                f"{resource_ref.resource_type.value}:{resource_ref.resource_id}({display_name})"
                for resource_ref, display_name in collision_refs
            )
            return None, f"GUID 在该项目存档内不唯一：{guid_text} -> {formatted}"

        resolved = index.guid_to_ref.get(guid_text)
        if resolved is None:
            return None, f"GUID 在该项目存档内不存在：package_id={package_id_text} guid={guid_text}"

        if expected_resource_types and resolved.resource_type not in expected_resource_types:
            expected_text = ", ".join(sorted(t.value for t in expected_resource_types))
            return (
                None,
                f"GUID 指向资源类型不匹配：guid={guid_text} 实际={resolved.resource_type.value} 期望={expected_text}",
            )

        return resolved, ""

    def resolve_guid(
        self,
        package_id: str,
        guid: str,
        *,
        expected_types: Optional[Sequence[ResourceType]] = None,
    ) -> ResourceRef:
        resolved, error_message = self.try_resolve_guid(
            package_id,
            guid,
            expected_types=expected_types,
        )
        if resolved is None:
            raise ValueError(error_message)
        return resolved

    def resolve_guid_global(
        self,
        guid: str,
        *,
        expected_types: Optional[Sequence[ResourceType]] = None,
        include_non_unique_in_package: bool = True,
    ) -> List[ScopedGuidMatch]:
        """全局 GUID 搜索：返回所有匹配（用于诊断/全局搜索 UI）。

        说明：
        - 若 include_non_unique_in_package=True，则即使某个 package 内 guid 不唯一，也会把冲突资源都列出；
        - 若为 False，则仅返回“在该 package 内唯一”的匹配（用于更严格的调用侧）。
        """

        guid_text = _normalize_text(guid)
        expected_resource_types = _normalize_expected_types(expected_types)

        if not guid_text:
            return []

        matches: List[ScopedGuidMatch] = []
        seen: Set[Tuple[str, ResourceType, str]] = set()

        for info in self._package_index_manager.list_packages():
            if not isinstance(info, dict):
                continue
            package_id_value = info.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value.strip():
                continue
            package_id_text = package_id_value.strip()

            index = self._guid_index_service.get_index(package_id_text)
            if not index.package_index_found:
                continue

            collision_refs = self._collect_collision_refs(index, guid_text)
            if collision_refs and not include_non_unique_in_package:
                continue

            # 1) 唯一映射（即使存在冲突，映射里也保留了第一个；全局模式下由 collision_refs 补齐）
            direct_match = index.guid_to_ref.get(guid_text)
            if direct_match is not None:
                if not expected_resource_types or direct_match.resource_type in expected_resource_types:
                    identity_key = (
                        package_id_text,
                        direct_match.resource_type,
                        direct_match.resource_id,
                    )
                    if identity_key not in seen:
                        matches.append(
                            ScopedGuidMatch(package_id=package_id_text, ref=direct_match)
                        )
                        seen.add(identity_key)

            # 2) 补齐冲突项（用于诊断展示）
            if include_non_unique_in_package and collision_refs:
                for resource_ref, _display_name in collision_refs:
                    if (
                        expected_resource_types
                        and resource_ref.resource_type not in expected_resource_types
                    ):
                        continue
                    identity_key = (
                        package_id_text,
                        resource_ref.resource_type,
                        resource_ref.resource_id,
                    )
                    if identity_key in seen:
                        continue
                    matches.append(
                        ScopedGuidMatch(package_id=package_id_text, ref=resource_ref)
                    )
                    seen.add(identity_key)

        return matches

    # ---------------------------------------------------------------------
    # 关卡变量（按包）
    # ---------------------------------------------------------------------

    def try_resolve_variable(
        self,
        package_id: str,
        variable_id: str,
    ) -> Tuple[Optional[Dict], str]:
        package_id_text = _normalize_text(package_id)
        variable_id_text = _normalize_text(variable_id)

        if not package_id_text:
            return None, "package_id 不能为空"
        if not variable_id_text:
            return None, "variable_id 不能为空"

        all_variables = self._level_variable_schema_view.get_all_variables() or {}
        payload = all_variables.get(variable_id_text)
        if payload is None:
            return None, f"关卡变量不存在：{variable_id_text}"

        if package_id_text in SPECIAL_GLOBAL_PACKAGE_IDS:
            return dict(payload), ""

        package_index = self._package_index_manager.load_package_index(package_id_text)
        if package_index is None:
            return None, f"未找到项目存档索引：{package_id_text}"

        resources_value = getattr(package_index, "resources", None)
        management_value = getattr(resources_value, "management", {}) if resources_value is not None else {}
        referenced_ids = management_value.get("level_variables", []) if isinstance(management_value, dict) else []

        referenced_id_set: Set[str] = set()
        if isinstance(referenced_ids, list):
            for entry in referenced_ids:
                if isinstance(entry, str) and entry.strip():
                    referenced_id_set.add(entry.strip())

        # 兼容两种语义：
        # - 现行约定：resources.management.level_variables 记录“变量文件 ID”（VARIABLE_FILE_ID）
        # - 兼容旧约定：直接记录 variable_id
        variable_file_id = _normalize_text(payload.get("variable_file_id"))
        is_referenced_by_file = bool(variable_file_id and variable_file_id in referenced_id_set)
        is_referenced_by_variable_id = variable_id_text in referenced_id_set

        if referenced_id_set and not (is_referenced_by_file or is_referenced_by_variable_id):
            return (
                None,
                "关卡变量未被当前项目存档引用："
                f"package_id={package_id_text} variable_id={variable_id_text} variable_file_id={variable_file_id or '<empty>'}",
            )

        return dict(payload), ""

    def resolve_variable(self, package_id: str, variable_id: str) -> Dict:
        payload, error_message = self.try_resolve_variable(package_id, variable_id)
        if payload is None:
            raise ValueError(error_message)
        return payload

    # ---------------------------------------------------------------------
    # 结构体（归一化）
    # ---------------------------------------------------------------------

    def try_resolve_struct(self, struct_id: str) -> Tuple[Optional[Dict], str]:
        struct_id_text = _normalize_text(struct_id)
        if not struct_id_text:
            return None, "struct_id 不能为空"

        payload = self._struct_repo.get_payload(struct_id_text)
        if payload is not None:
            return payload, ""

        errors = self._struct_repo.get_errors()
        if struct_id_text in errors:
            return None, errors[struct_id_text]

        return None, f"结构体定义不存在：{struct_id_text}"

    def resolve_struct(self, struct_id: str) -> Dict:
        payload, error_message = self.try_resolve_struct(struct_id)
        if payload is None:
            raise ValueError(error_message)
        return payload

    def try_resolve_custom_variable_field_path(
        self,
        package_id: str,
        variable_id: str,
        field_path: str,
    ) -> Tuple[Optional[str], str]:
        """校验“结构体/结构体列表变量”的字段路径是否有效。

        当前约定：
        - field_path 暂只支持单层字段名（不支持 a.b.c 的多段路径）。
        """

        field_path_text = _normalize_text(field_path)
        if not field_path_text:
            return None, "field_path 不能为空"
        if "." in field_path_text:
            return None, f"暂不支持多段字段路径：{field_path_text}"

        variable_payload, error_message = self.try_resolve_variable(package_id, variable_id)
        if variable_payload is None:
            return None, error_message

        variable_type = _normalize_text(variable_payload.get("variable_type"))
        if variable_type not in {"结构体", "结构体列表"}:
            return None, f"变量类型不是结构体/结构体列表：{variable_id} -> {variable_type or '<empty>'}"

        struct_id_text = ""
        default_value = variable_payload.get("default_value")
        if isinstance(default_value, dict):
            struct_id_text = _normalize_text(
                default_value.get("struct_id") or default_value.get("structId")
            )
        metadata_value = variable_payload.get("metadata")
        if not struct_id_text and isinstance(metadata_value, dict):
            struct_id_text = _normalize_text(metadata_value.get("struct_id") or metadata_value.get("structId"))

        if not struct_id_text:
            return None, f"结构体变量缺少 struct_id（无法校验字段路径）：{variable_id}"

        struct_payload, error_message = self.try_resolve_struct(struct_id_text)
        if struct_payload is None:
            return None, error_message

        field_names = set(self._struct_repo.get_field_names(struct_id_text))
        if field_path_text not in field_names:
            preview = ", ".join(list(sorted(field_names))[:10])
            return (
                None,
                f"字段不存在：struct_id={struct_id_text} field={field_path_text}（可用字段示例：{preview}）",
            )

        return field_path_text, ""


