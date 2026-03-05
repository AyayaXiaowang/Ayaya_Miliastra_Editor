from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from engine.configs.resource_types import ResourceType
from engine.resources.package_index import PackageIndex


@dataclass(frozen=True)
class ResourceRef:
    """指向资源库中某个资源的稳定引用。"""

    resource_type: ResourceType
    resource_id: str


@dataclass(frozen=True)
class GuidCollision:
    """同一 package 内出现重复 guid 时的冲突记录（包含两端资源定位信息）。"""

    guid: str
    first: ResourceRef
    second: ResourceRef
    first_name: str
    second_name: str


@dataclass(frozen=True)
class PackageGuidIndex:
    """包内 GUID 派生索引（只读快照）。

    约定：
    - guid 的作用域为 package 内（跨 package 可重复）。
    - 索引只收录“确实携带 guid 的资源”；guid 为空时不进入索引。
    - `collisions` 仅用于校验与诊断；resolve 时不做“取第一个”的隐式策略。
    """

    package_id: str
    guid_to_ref: Dict[str, ResourceRef]
    collisions: List[GuidCollision]
    missing_resources: List[ResourceRef]
    package_index_found: bool


def iter_package_guid_candidates(package_index: PackageIndex) -> Iterable[ResourceRef]:
    """枚举一个项目存档内“可能携带 guid”的候选资源引用。

    当前覆盖：
    - templates（ResourceType.TEMPLATE）
    - instances（ResourceType.INSTANCE）
    - level_entity_id（ResourceType.INSTANCE）
    """

    templates_value = getattr(getattr(package_index, "resources", None), "templates", []) or []
    if isinstance(templates_value, list):
        for template_id in templates_value:
            if isinstance(template_id, str) and template_id.strip():
                yield ResourceRef(ResourceType.TEMPLATE, template_id.strip())

    instances_value = getattr(getattr(package_index, "resources", None), "instances", []) or []
    if isinstance(instances_value, list):
        for instance_id in instances_value:
            if isinstance(instance_id, str) and instance_id.strip():
                yield ResourceRef(ResourceType.INSTANCE, instance_id.strip())

    level_entity_id_value = getattr(package_index, "level_entity_id", None)
    if isinstance(level_entity_id_value, str) and level_entity_id_value.strip():
        yield ResourceRef(ResourceType.INSTANCE, level_entity_id_value.strip())


def build_package_guid_index(
    package_id: str,
    package_index: PackageIndex,
    *,
    resource_manager,
) -> PackageGuidIndex:
    """构建包内 GUID 派生索引。

    注意：
    - 该函数不抛出“缺资源”异常；缺失资源会进入 `missing_resources` 供校验层处理。
    - 重复 guid 不会覆盖已有条目，而是记录到 `collisions`。
    """

    guid_to_ref: Dict[str, ResourceRef] = {}
    guid_to_name: Dict[str, str] = {}
    collisions: List[GuidCollision] = []
    missing_resources: List[ResourceRef] = []
    seen_resource_refs: set[tuple[ResourceType, str]] = set()

    def normalize_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()

    for resource_ref in iter_package_guid_candidates(package_index):
        ref_key = (resource_ref.resource_type, resource_ref.resource_id)
        if ref_key in seen_resource_refs:
            continue
        seen_resource_refs.add(ref_key)

        metadata = resource_manager.get_resource_metadata(
            resource_ref.resource_type, resource_ref.resource_id
        )
        if not isinstance(metadata, dict):
            missing_resources.append(resource_ref)
            continue

        guid_text = normalize_text(metadata.get("guid"))
        if not guid_text:
            continue

        display_name = normalize_text(metadata.get("name")) or resource_ref.resource_id

        existing = guid_to_ref.get(guid_text)
        if existing is None:
            guid_to_ref[guid_text] = resource_ref
            guid_to_name[guid_text] = display_name
            continue

        # 重复 guid：记录冲突（不覆盖）
        collisions.append(
            GuidCollision(
                guid=guid_text,
                first=existing,
                second=resource_ref,
                first_name=guid_to_name.get(guid_text, existing.resource_id),
                second_name=display_name,
            )
        )

    return PackageGuidIndex(
        package_id=package_id,
        guid_to_ref=guid_to_ref,
        collisions=collisions,
        missing_resources=missing_resources,
        package_index_found=True,
    )


class PackageGuidIndexService:
    """包内 GUID 派生索引服务（带进程内缓存）。"""

    def __init__(self, *, resource_manager, package_index_manager) -> None:
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        # {package_id: (resources_fingerprint, PackageGuidIndex)}
        self._cache: Dict[str, Tuple[str, PackageGuidIndex]] = {}

    def invalidate_cache(self) -> None:
        self._cache.clear()

    def get_index(self, package_id: str) -> PackageGuidIndex:
        package_id_text = str(package_id or "").strip()
        if not package_id_text:
            return PackageGuidIndex(
                package_id="",
                guid_to_ref={},
                collisions=[],
                missing_resources=[],
                package_index_found=False,
            )

        resources_fingerprint = str(
            self._resource_manager.get_resource_library_fingerprint() or ""
        )
        cached_entry = self._cache.get(package_id_text)
        if cached_entry is not None and cached_entry[0] == resources_fingerprint:
            return cached_entry[1]

        package_index = self._package_index_manager.load_package_index(package_id_text)
        if package_index is None:
            index = PackageGuidIndex(
                package_id=package_id_text,
                guid_to_ref={},
                collisions=[],
                missing_resources=[],
                package_index_found=False,
            )
            self._cache[package_id_text] = (resources_fingerprint, index)
            return index

        index = build_package_guid_index(
            package_id_text,
            package_index,
            resource_manager=self._resource_manager,
        )
        self._cache[package_id_text] = (resources_fingerprint, index)
        return index


