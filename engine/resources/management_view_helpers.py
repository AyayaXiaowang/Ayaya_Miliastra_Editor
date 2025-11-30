"""管理配置视图辅助模块。

集中维护 `ManagementData` 字段与 `ResourceType` 的映射，以及
在 `PackageView` / `GlobalResourceView` / `UnclassifiedResourceView`
之间共享的“单一配置体”管理域约定，避免多处硬编码。
"""

from __future__ import annotations

from engine.configs.resource_types import ResourceType


# 统一的 ManagementData 字段 -> ResourceType 映射。
MANAGEMENT_FIELD_TO_RESOURCE_TYPE: dict[str, ResourceType] = {
    "timers": ResourceType.TIMER,
    "level_variables": ResourceType.LEVEL_VARIABLE,
    "preset_points": ResourceType.PRESET_POINT,
    "skill_resources": ResourceType.SKILL_RESOURCE,
    "currency_backpack": ResourceType.CURRENCY_BACKPACK,
    "equipment_data": ResourceType.EQUIPMENT_DATA,
    "shop_templates": ResourceType.SHOP_TEMPLATE,
    "ui_layouts": ResourceType.UI_LAYOUT,
    "ui_widget_templates": ResourceType.UI_WIDGET_TEMPLATE,
    "multi_language": ResourceType.MULTI_LANGUAGE,
    "main_cameras": ResourceType.MAIN_CAMERA,
    "light_sources": ResourceType.LIGHT_SOURCE,
    "background_music": ResourceType.BACKGROUND_MUSIC,
    "paths": ResourceType.PATH,
    "entity_deployment_groups": ResourceType.ENTITY_DEPLOYMENT_GROUP,
    "unit_tags": ResourceType.UNIT_TAG,
    "scan_tags": ResourceType.SCAN_TAG,
    "shields": ResourceType.SHIELD,
    "peripheral_systems": ResourceType.PERIPHERAL_SYSTEM,
    "save_points": ResourceType.SAVE_POINT,
    "chat_channels": ResourceType.CHAT_CHANNEL,
    "level_settings": ResourceType.LEVEL_SETTINGS,
}


# 视为“单一配置体”的管理域字段名集合：UI 中按一份聚合配置体编辑。
SINGLE_CONFIG_MANAGEMENT_FIELDS: set[str] = {
    "currency_backpack",
    "peripheral_systems",
    "save_points",
    "level_settings",
}


