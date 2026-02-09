"""资源文件名策略（统一真源）。

本模块用于集中维护“资源 name 与物理文件名”的关系规则，避免：
- 扫描阶段按文件名回写 JSON 的 name
- 保存阶段按 id_to_filename_cache 沿用旧文件名
两套规则互相冲突，导致 UI 改名被扫描回滚。

核心结论：
- 大多数资源类型允许 `payload["name"]` 与文件名解耦（保存优先沿用缓存文件名，避免频繁重命名）。
- 仅少数“管理配置/多记录类”资源在保存时明确以业务名称驱动物理文件名；这些类型才允许扫描期做
  “文件名 -> name”的回写同步（用于覆盖用户在资源库中手动改文件名的情况）。
"""

from __future__ import annotations

from engine.configs.resource_types import ResourceType


# 保存时以“业务名称”驱动物理文件名的资源类型集合：
# - 这些类型在 `ResourceFileOps.get_resource_file_path()` 中会无视 id_to_filename_cache，优先按 name 生成文件名；
# - 因此，扫描阶段若发现“文件名与 name 不一致”，可安全地以文件名为准回写 name（视为用户手动改名）。
_RESOURCE_TYPES_PREFER_NAME_OVER_CACHED_FILENAME: set[ResourceType] = {
    ResourceType.CHAT_CHANNEL,
    ResourceType.EQUIPMENT_DATA,
    ResourceType.MAIN_CAMERA,
    ResourceType.PRESET_POINT,
    ResourceType.PERIPHERAL_SYSTEM,
    ResourceType.SAVE_POINT,
    # 多条记录的管理配置
    ResourceType.TIMER,
    ResourceType.LEVEL_VARIABLE,
    ResourceType.SKILL_RESOURCE,
    ResourceType.SHOP_TEMPLATE,
    ResourceType.PATH,
    ResourceType.BACKGROUND_MUSIC,
    ResourceType.LIGHT_SOURCE,
    ResourceType.ENTITY_DEPLOYMENT_GROUP,
    ResourceType.UNIT_TAG,
    ResourceType.SCAN_TAG,
    ResourceType.SHIELD,
    ResourceType.UI_LAYOUT,
    ResourceType.UI_WIDGET_TEMPLATE,
    ResourceType.UI_PAGE,
}


def resource_type_prefers_name_over_cached_filename(resource_type: ResourceType) -> bool:
    """该资源类型在保存时是否应“以 name 驱动物理文件名”（覆盖缓存文件名）。"""

    return resource_type in _RESOURCE_TYPES_PREFER_NAME_OVER_CACHED_FILENAME


def resource_type_should_sync_json_name_with_filename(resource_type: ResourceType) -> bool:
    """扫描阶段是否允许把 JSON 的 name 回写为文件名。

    只有当保存策略也明确“以 name 驱动物理文件名”时，扫描期才允许做该同步；
    否则会与“沿用缓存文件名”的默认策略冲突，造成 UI 改名被回滚。
    """

    return resource_type_prefers_name_over_cached_filename(resource_type)


