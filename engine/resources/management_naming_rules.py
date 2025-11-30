"""管理配置与战斗预设资源的 ID / 显示名字段约定。

本模块集中维护 `ResourceType` 对应的：
- 资源 ID 字段名（如 timer_id / variable_id / resource_id）
- 业务显示名称字段名（如 timer_name / variable_name / resource_name）

用途：
- `ResourceIndexBuilder._extract_id_and_name_from_json`：在扫描 JSON 时
  使用稳定的 ID 字段而不是物理文件名，支持“用名字命名文件、用 ID 做引用”。
- `ResourceManager.save_resource`：在保存管理配置时补全 `name` 字段，
  以业务名称作为物理文件名的依据。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine.configs.resource_types import ResourceType


# ResourceType -> 稳定 ID 所在字段名
ID_FIELDS_BY_TYPE: Dict[ResourceType, str] = {
    # 基础模板/实例与战斗预设
    ResourceType.TEMPLATE: "template_id",
    ResourceType.INSTANCE: "instance_id",
    ResourceType.PLAYER_TEMPLATE: "template_id",
    ResourceType.PLAYER_CLASS: "class_id",
    ResourceType.UNIT_STATUS: "status_id",
    ResourceType.SKILL: "skill_id",
    ResourceType.PROJECTILE: "projectile_id",
    ResourceType.ITEM: "item_id",
    # 管理配置 - 多条记录
    ResourceType.TIMER: "timer_id",
    ResourceType.LEVEL_VARIABLE: "variable_id",
    ResourceType.UI_LAYOUT: "layout_id",
    ResourceType.UI_WIDGET_TEMPLATE: "template_id",
    ResourceType.SKILL_RESOURCE: "resource_id",
    ResourceType.EQUIPMENT_DATA: "equipment_id",
    ResourceType.SHOP_TEMPLATE: "shop_id",
    ResourceType.BACKGROUND_MUSIC: "music_id",
    ResourceType.LIGHT_SOURCE: "light_id",
    ResourceType.PATH: "path_id",
    ResourceType.ENTITY_DEPLOYMENT_GROUP: "group_id",
    ResourceType.UNIT_TAG: "tag_id",
    ResourceType.SCAN_TAG: "scan_tag_id",
    ResourceType.SHIELD: "shield_id",
    ResourceType.PERIPHERAL_SYSTEM: "system_id",
    ResourceType.SAVE_POINT: "save_point_id",
    ResourceType.CHAT_CHANNEL: "channel_id",
    # 管理配置 - 单配置体
    ResourceType.CURRENCY_BACKPACK: "config_id",
    ResourceType.LEVEL_SETTINGS: "config_id",
}


# ResourceType -> 业务显示名称字段名
DISPLAY_NAME_FIELDS_BY_TYPE: Dict[ResourceType, str] = {
    # 战斗预设
    ResourceType.PLAYER_TEMPLATE: "template_name",
    ResourceType.PLAYER_CLASS: "class_name",
    ResourceType.UNIT_STATUS: "status_name",
    ResourceType.SKILL: "skill_name",
    ResourceType.PROJECTILE: "projectile_name",
    ResourceType.ITEM: "item_name",
    # 管理配置 - 多条记录
    ResourceType.TIMER: "timer_name",
    ResourceType.LEVEL_VARIABLE: "variable_name",
    ResourceType.UI_LAYOUT: "layout_name",
    ResourceType.UI_WIDGET_TEMPLATE: "template_name",
    ResourceType.SKILL_RESOURCE: "resource_name",
    ResourceType.EQUIPMENT_DATA: "equipment_name",
    ResourceType.SHOP_TEMPLATE: "shop_name",
    ResourceType.BACKGROUND_MUSIC: "music_name",
    ResourceType.LIGHT_SOURCE: "light_name",
    ResourceType.PATH: "path_name",
    ResourceType.ENTITY_DEPLOYMENT_GROUP: "group_name",
    ResourceType.UNIT_TAG: "tag_name",
    ResourceType.SCAN_TAG: "scan_tag_name",
    ResourceType.SHIELD: "shield_name",
    ResourceType.PERIPHERAL_SYSTEM: "system_name",
    ResourceType.SAVE_POINT: "save_point_name",
    ResourceType.CHAT_CHANNEL: "channel_name",
    # 管理配置 - 单配置体
    ResourceType.LEVEL_SETTINGS: "level_name",
}


def get_id_field_for_type(resource_type: ResourceType) -> Optional[str]:
    """返回给定资源类型对应的 ID 字段名（若无明确约定则返回 None）。"""
    return ID_FIELDS_BY_TYPE.get(resource_type)


def get_display_name_field_for_type(resource_type: ResourceType) -> Optional[str]:
    """返回给定资源类型对应的业务显示名称字段名（若无则返回 None）。"""
    return DISPLAY_NAME_FIELDS_BY_TYPE.get(resource_type)


def get_id_and_display_name_fields(
    resource_type: ResourceType,
) -> Tuple[Optional[str], Optional[str]]:
    """同时返回 ID 与显示名字段名元组。"""
    return get_id_field_for_type(resource_type), get_display_name_field_for_type(resource_type)


